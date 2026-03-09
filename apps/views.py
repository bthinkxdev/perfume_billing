# apps/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from decimal import Decimal
from datetime import datetime, timedelta
import json
from django.db import transaction
from .models import (
    Invoice,
    InvoiceItem,
    Product,
    Customer,
    Payment,
    CompanyProfile,
    PriceOverrideLog,
    ActivityLog,
    get_config,
)
from .permissions import permission_required
from .forms import AppConfigForm, CONFIG_SECTIONS
from .configuration import parse_decimal


# ==================== DASHBOARD ====================
@login_required
def dashboard(request):
    today = timezone.now().date()

    range_type = request.GET.get('range', '7d')

    if range_type == '1m':
        days = 30
    elif range_type == '3m':
        days = 90
    else:
        days = 7  # default

    start_date = today - timedelta(days=days - 1)

    # Sales chart data
    sales_chart = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        daily_total = Invoice.objects.filter(
            invoice_date__date=date,
            status='CONFIRMED'
        ).aggregate(total=Sum('grand_total'))['total'] or 0

        sales_chart.append({
            'date': date.strftime('%d %b'),
            'amount': float(daily_total)
        })

    # Existing stats (unchanged)
    today_sales = Invoice.objects.filter(
        invoice_date__date=today,
        status='CONFIRMED'
    ).aggregate(total=Sum('grand_total'), count=Count('id'))

    month_sales = Invoice.objects.filter(
        invoice_date__date__gte=today - timedelta(days=30),
        status='CONFIRMED'
    ).aggregate(total=Sum('grand_total'), count=Count('id'))

    outstanding = Customer.objects.aggregate(
        total=Sum('outstanding_balance')
    )['total'] or 0
    
    # Low stock products
    low_stock = Product.objects.filter(
        is_active=True,
        stock_qty__lte=F('reorder_level')
    ).filter(
        Q(is_from_LPO=False) |
        Q(is_from_LPO=True, received_LPO=True)
    ).count()
    # Purchases last 30 days for quick insight
    from .models import PurchaseOrder
    month_purchases = PurchaseOrder.objects.filter(
        order_date__gte=today - timedelta(days=30),
        status__in=['ORDERED', 'RECEIVED']
    ).aggregate(total=Sum('grand_total'), count=Count('id'))

    recent_invoices = Invoice.objects.filter(
        status='CONFIRMED'
    ).select_related('customer').order_by('-invoice_date')[:10]
 # Top selling products this month
    top_products = InvoiceItem.objects.filter(
        invoice__invoice_date__date__gte=today - timedelta(days=30),
        invoice__status='CONFIRMED'
    ).values(
        'product__sku',
        'product__description'
    ).annotate(
        total_qty=Sum('quantity'),
        total_amount=Sum('amount')
    ).order_by('-total_amount')[:10]
    context = {
        'today_sales': today_sales['total'] or 0,
        'today_count': today_sales['count'],
        'month_sales': month_sales['total'] or 0,
        'month_count': month_sales['count'],
        'month_purchases': month_purchases['total'] or 0,
        'month_purchase_count': month_purchases['count'],
        'outstanding': outstanding,
        'low_stock': low_stock,
        'recent_invoices': recent_invoices,
        'top_products': top_products,
        'sales_chart': json.dumps(sales_chart),
        'active_range': range_type,
    }
    
    return render(request, 'dashboard.html', context)


@login_required
@permission_required("settings.manage")
def system_settings_view(request):
    """
    Configure global system settings.
    Only users with the logical `settings.manage` permission may access this view.
    """
    config = get_config()
    if request.method == "POST":
        form = AppConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Application configuration updated successfully.")
            return redirect("apps:system_settings")
        messages.error(request, "Please correct the validation errors below.")
    else:
        form = AppConfigForm(instance=config)

    sections = [
        (title, [form[field_name] for field_name in field_names])
        for title, field_names in CONFIG_SECTIONS
    ]
    context = {"form": form, "sections": sections}
    return render(request, "settings.html", context)


# ==================== NEW BILL ====================
@login_required
def new_bill(request):
    """Create new invoice"""
    company = CompanyProfile.get_company()
    customers = Customer.objects.filter(is_active=True).order_by('name')
    
    config = get_config()
    context = {
        'company': company,
        'customers': customers,
        'today': timezone.now().date().strftime('%Y-%m-%d'),
        'default_payment_term': config.default_payment_term,
    }
    
    return render(request, 'new_bill.html', context)


@login_required
@require_http_methods(["POST"])
def save_invoice(request):
    try:
        config = get_config()
        data = json.loads(request.body)
        customer = get_object_or_404(Customer, id=data['customer_id'])

        # ---------- PRE-CHECK CREDIT (BEFORE DB WRITE) ----------
        temp_subtotal = Decimal(0)

        for item in data['items']:
            qty = Decimal(item['quantity'])
            price = Decimal(item['unit_price'])
            temp_subtotal += qty * price

        discount = Decimal(data.get('discount_amount', 0))
        if discount < 0:
            return JsonResponse({
                'success': False,
                'error': 'Discount cannot be negative'
            }, status=400)
        # Enforce max discount percentage from settings
        max_disc = config.max_discount_percentage
        if max_disc >= 0:
            max_allowed_discount = (temp_subtotal * max_disc) / Decimal("100")
            if discount > max_allowed_discount:
                return JsonResponse(
                    {
                        "success": False,
                        "error": f"Discount cannot exceed {max_disc}% of subtotal",
                    },
                    status=400,
                )

        # If bill-level discounting is disabled, block any discount
        if discount > 0 and not config.enable_bill_level_discount:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Bill-level discounts are disabled in system settings.",
                },
                status=400,
            )
        grand_total = temp_subtotal - discount

        # ---------- PRE-CHECK CREDIT (BLOCK DRAFT + CONFIRM) ----------
        payment_terms = data['payment_terms']
        if payment_terms not in ['CASH', 'CREDIT']:
            return JsonResponse({
                'success': False,
                'error': 'Invalid payment terms. Use CASH or CREDIT.'
            }, status=400)

        # Enforce credit sales toggle
        if payment_terms == "CREDIT" and not config.enable_credit_sales:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Credit sales are disabled in system settings.",
                },
                status=400,
            )

        # Normalize paid amount rules
        if payment_terms == 'CASH':
            paid_amount = grand_total  # full payment required
        else:
            paid_amount = Decimal(data.get('paid_amount', 0))
            if paid_amount < 0:
                return JsonResponse({
                    'success': False,
                    'error': 'Paid amount cannot be negative'
                }, status=400)
            if paid_amount > grand_total:
                return JsonResponse({
                    'success': False,
                    'error': 'Paid amount cannot exceed grand total'
                }, status=400)

        balance_due = grand_total - paid_amount

        warning = None
        if payment_terms == "CREDIT" and balance_due > 0:
            block_credit = config.block_credit_if_limit_exceeded
            warn_only = config.credit_warning_only

            can_take = customer.can_take_credit(balance_due)
            available = customer.get_available_credit()

            if block_credit and not can_take:
                return JsonResponse(
                    {
                        "success": False,
                        "error": (
                            "Insufficient credit. "
                            f"Available credit: {available}"
                        ),
                    },
                    status=400,
                )
            if warn_only and not can_take:
                warning = (
                    "Credit limit exceeded. "
                    f"Available credit: {available}"
                )
        # ---------- DB TRANSACTION ----------
        with transaction.atomic():

            invoice = Invoice.objects.create(
                customer=customer,
                payment_terms=payment_terms,
                discount_amount=discount,
                paid_amount=paid_amount,
                notes=data.get('notes', ''),
                created_by=request.user,
                status='DRAFT'
            )

            allow_override = config.allow_price_override
            max_override_pct = config.max_price_override_limit

            for idx, item_data in enumerate(data['items'], 1):
                product = get_object_or_404(Product, id=item_data['product_id'])

                unit_price = Decimal(item_data['unit_price'])
                quantity = Decimal(item_data['quantity'])

                default_price = product.get_default_price(customer.customer_type)
                is_overridden = unit_price != default_price

                if not config.allow_negative_stock and quantity > product.stock_qty:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": (
                                f"Insufficient stock for {product.sku}. "
                                f"Available: {product.stock_qty}, required: {quantity}."
                            ),
                        },
                        status=400,
                    )

                # Enforce price override rules
                if is_overridden and not allow_override:
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Price override is disabled in system settings.",
                        },
                        status=400,
                    )

                if (
                    is_overridden
                    and default_price
                    and default_price != 0
                ):
                    diff_pct = (
                        abs(unit_price - default_price)
                        / default_price
                        * Decimal("100")
                    )
                    if diff_pct > max_override_pct:
                        return JsonResponse(
                            {
                                "success": False,
                                "error": (
                                    "Price override exceeds allowed limit "
                                    f"of {max_override_pct}%."
                                ),
                            },
                            status=400,
                        )

                invoice_item = InvoiceItem.objects.create(
                    invoice=invoice,
                    serial_no=idx,
                    product=product,
                    barcode=product.barcode or '',
                    item_no=product.sku,
                    description=product.description,
                    quantity=quantity,
                    unit_price=unit_price,
                    is_price_overridden=is_overridden,
                    original_price=default_price if is_overridden else None
                )

                if is_overridden:
                    PriceOverrideLog.objects.create(
                        invoice_item=invoice_item,
                        product=product,
                        customer=customer,
                        original_price=default_price,
                        overridden_price=unit_price,
                        user=request.user
                    )

            invoice.calculate_totals()

            if data.get('confirm', False):
                invoice.confirm_invoice(request.user)

                ActivityLog.log_activity(
                    user=request.user,
                    action_type='CREATE',
                    model_name='Invoice',
                    object_id=invoice.invoice_number,
                    description=f'Created and confirmed invoice {invoice.invoice_number}',
                    request=request
                )

        response = {
            "success": True,
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "message": "Invoice saved successfully",
        }
        if warning:
            response["warning"] = warning

        return JsonResponse(response)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def search_product(request):
    """Search product by barcode or SKU via AJAX"""
    query = request.GET.get('q', '').strip()
    
    if not query:
        return JsonResponse({'success': False, 'error': 'No query provided'})
    
    # Search by barcode first, then SKU, then description
    product = Product.objects.filter(
        Q(is_from_LPO=False) |
        Q(is_from_LPO=True, received_LPO=True),
        Q(barcode=query) | Q(sku=query),
        is_active=True
    ).first()
        
    if not product:
        # Try fuzzy search in description
        product = Product.objects.filter(
            description__icontains=query,
            is_active=True
        ).first()
    
    if product:
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'sku': product.sku,
                'barcode': product.barcode or '',
                'description': product.description,
                'stock_qty': float(product.stock_qty),
                'wholesale_price': float(product.wholesale_price),
                'retail_price': float(product.retail_price),
            }
        })
    
    return JsonResponse({
        'success': False,
        'error': 'Product not found'
    })


@login_required
def search_customer(request):
    """Search customer by phone or name via AJAX"""
    query = request.GET.get('q', '').strip()
    
    if not query:
        return JsonResponse({'customers': []})
    
    customers = Customer.objects.filter(
        Q(phone__icontains=query) | Q(name__icontains=query) | Q(customer_id__icontains=query),
        is_active=True
    ).order_by('name')[:10]
    
    customer_list = [{
        'id': c.id,
        'customer_id': c.customer_id,
        'name': c.name,
        'display_name': c.name or c.company_name or c.phone or c.customer_id,
        'company_name': c.company_name,
        'phone': c.phone,
        'customer_type': c.customer_type,
        'outstanding_balance': float(c.outstanding_balance),
        'credit_limit': float(c.credit_limit),
        'available_credit': float(c.get_available_credit()),
        'discount_percent': float(c.discount_percent),
    } for c in customers]
    print("customer_list :",customer_list)
    return JsonResponse({'customers': customer_list})


@login_required
@require_http_methods(["POST"])
def quick_add_customer(request):
    """Quick add customer via AJAX"""
    try:
        config = get_config()
        data = json.loads(request.body)
        discount_percent = Decimal(data.get('discount_percent', 0))
        if discount_percent < 0 or discount_percent > 100:
            return JsonResponse({
                'success': False,
                'error': 'Discount percentage must be between 0 and 100'
            }, status=400)
        
        # Use default credit limit from settings when not provided
        credit_limit_raw = data.get("credit_limit")
        if credit_limit_raw in (None, "", "null"):
            credit_limit_raw = config.default_credit_limit

        customer = Customer.objects.create(
            name=data['name'],
            company_name=data.get('company_name', ''),
            phone=data['phone'],
            email=data.get('email', ''),
            address=data.get('address', ''),
            customer_type=data.get('customer_type', 'WHOLESALE'),
            credit_limit=parse_decimal(credit_limit_raw, "credit_limit"),
            discount_percent=discount_percent
        )
        
        return JsonResponse({
            'success': True,
            'customer': {
                'id': customer.id,
                'customer_id': customer.customer_id,
                'name': customer.name,
                'display_name': customer.name or customer.phone or customer.customer_id,
                'company_name': customer.company_name,
                'phone': customer.phone,
                'customer_type': customer.customer_type,
                'outstanding_balance': float(customer.outstanding_balance),
                'credit_limit': float(customer.credit_limit),
                'available_credit': float(customer.get_available_credit()),
                'discount_percent': float(customer.discount_percent),
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


# ==================== INVOICES LIST ====================
@login_required
def invoices_list(request):
    """List all invoices with filters"""
    invoices = Invoice.objects.all().select_related('customer', 'created_by')
    
    # Filters
    status = request.GET.get('status')
    if status:
        invoices = invoices.filter(status=status)
    
    payment_terms = request.GET.get('payment_terms')
    if payment_terms:
        invoices = invoices.filter(payment_terms=payment_terms)
    
    customer_id = request.GET.get('customer')
    if customer_id:
        invoices = invoices.filter(customer_id=customer_id)
    
    date_from = request.GET.get('date_from')
    if date_from:
        invoices = invoices.filter(invoice_date__date__gte=date_from)
    
    date_to = request.GET.get('date_to')
    if date_to:
        invoices = invoices.filter(invoice_date__date__lte=date_to)
    
    search = request.GET.get('search')
    if search:
        invoices = invoices.filter(
            Q(invoice_number__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search)
        )
    
    # Outstanding only
    if request.GET.get('outstanding'):
        invoices = invoices.filter(balance_due__gt=0)
    
    invoices = invoices.order_by('-invoice_date')
    
    # Pagination (simple)
    page = int(request.GET.get('page', 1))
    per_page = 50
    start = (page - 1) * per_page
    end = start + per_page
    
    total_count = invoices.count()
    invoices = invoices[start:end]
    
    # For filters
    customers = Customer.objects.filter(is_active=True).order_by('name')
    
    context = {
        'invoices': invoices,
        'customers': customers,
        'total_count': total_count,
        'page': page,
        'has_next': end < total_count,
        'has_prev': page > 1,
    }
    
    return render(request, 'invoices_list.html', context)


@login_required
def invoice_detail(request, invoice_id):
    """View invoice detail"""
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer', 'created_by'),
        id=invoice_id
    )
    items = invoice.items.select_related('product').all()
    payments = invoice.payments.select_related('created_by').all()
    company = CompanyProfile.get_company()
    
    context = {
        'invoice': invoice,
        'items': items,
        'payments': payments,
        'company': company,
    }
    
    return render(request, 'invoice_detail.html', context)


@login_required
def invoice_print(request, invoice_id):
    """Print invoice"""
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer'),
        id=invoice_id
    )
    items = invoice.items.select_related('product').all()
    company = CompanyProfile.get_company()

    config = get_config()
    # System settings affecting invoice print/layout
    invoice_print_size = config.invoice_print_size
    show_barcode = config.show_barcode_on_invoice
    show_item_number = config.show_item_number_on_invoice
    footer_text = config.invoice_footer_text

    # Log print activity
    ActivityLog.log_activity(
        user=request.user,
        action_type='PRINT',
        model_name='Invoice',
        object_id=invoice.invoice_number,
        description=f'Printed invoice {invoice.invoice_number}',
        request=request
    )
    
    context = {
        "invoice": invoice,
        "items": items,
        "company": company,
        "invoice_print_size": invoice_print_size,
        "show_barcode": show_barcode,
        "show_item_number": show_item_number,
        "invoice_footer_text": footer_text,
    }
    
    return render(request, 'invoice_print.html', context)


@login_required
@permission_required('billing.cancel_invoice', as_json=True)
@require_http_methods(["POST"])
def cancel_invoice(request, invoice_id):
    """Cancel invoice"""
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if invoice.status == 'CANCELLED':
        return JsonResponse({
            'success': False,
            'error': 'Invoice is already cancelled'
        })

    # If CONFIRMED → restore stock & ledger
    if invoice.status == 'CONFIRMED':
        invoice.cancel_invoice(request.user)

    # If DRAFT → just mark cancelled
    if invoice.status == 'DRAFT':
        invoice.status = 'CANCELLED'
        invoice.save(update_fields=['status'])

    ActivityLog.log_activity(
        user=request.user,
        action_type='CANCEL',
        model_name='Invoice',
        object_id=invoice.invoice_number,
        description=f'Cancelled invoice {invoice.invoice_number}',
        request=request
    )
    return JsonResponse({
        'success': True,
        'message': 'Invoice cancelled successfully'
    })
    
@login_required
@require_http_methods(["POST"])
def confirm_draft_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    config = get_config()

    if invoice.status != 'DRAFT':
        return JsonResponse({
            'success': False,
            'error': 'Only draft invoices can be confirmed'
        })

    # Credit check (same as save_invoice)
    if invoice.payment_terms == 'CREDIT' and invoice.balance_due > 0:
        customer = invoice.customer
        if config.block_credit_if_limit_exceeded and not customer.can_take_credit(invoice.balance_due):
            return JsonResponse({
                'success': False,
                'error': f'Credit limit exceeded. Available credit: {customer.get_available_credit()}'
            })

    # Confirm invoice (this already deducts stock & updates ledger)
    invoice.confirm_invoice(request.user)

    ActivityLog.log_activity(
        user=request.user,
        action_type='UPDATE',
        model_name='Invoice',
        object_id=invoice.invoice_number,
        description=f'Confirmed draft invoice {invoice.invoice_number}',
        request=request
    )

    return JsonResponse({
        'success': True,
        'message': 'Invoice confirmed successfully'
    })


# ==================== AUTHENTICATION ====================
@login_required
@require_http_methods(["POST"])
def user_logout(request):
    """Log out the current user and redirect to login page"""
    logout(request)
    return redirect('/login/')  # Redirect to app login page



