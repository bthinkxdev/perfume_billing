from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count, F, DecimalField
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone
from django.http import JsonResponse
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from .models import (
    Invoice, Payment, Product, Customer, InvoiceItem,
    ActivityLog, StockAdjustment, CompanyProfile
)

# ==================== PAYMENTS ====================

@login_required
def payment_entry(request, invoice_id=None):
    """Record payment against invoice"""
    invoice = None
    if invoice_id:
        invoice = get_object_or_404(Invoice, pk=invoice_id)
    
    if request.method == 'POST':
        try:
            # Get invoice if not already set
            if not invoice:
                invoice_id = request.POST.get('invoice')
                invoice = Invoice.objects.get(id=invoice_id)
            
            amount = Decimal(request.POST.get('amount'))
            
            # Validate amount
            if amount <= 0:
                messages.error(request, 'Payment amount must be greater than zero!')
                return redirect(request.path)
            
            if amount > invoice.balance_due:
                messages.error(request, f'Payment amount cannot exceed balance due ({invoice.balance_due})!')
                return redirect(request.path)
            
            # Create payment
            payment = Payment.objects.create(
                invoice=invoice,
                customer=invoice.customer,
                amount=amount,
                payment_method=request.POST.get('payment_method'),
                reference_no=request.POST.get('reference_no', ''),
                notes=request.POST.get('notes', ''),
                created_by=request.user
            )
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='CREATE',
                model_name='Payment',
                object_id=payment.id,
                description=f"Payment received: {payment.payment_id} - Amount: {amount}",
                request=request
            )
            
            messages.success(request, f'Payment of {amount} recorded successfully!')
            return redirect('apps:payments_list')
            
        except Invoice.DoesNotExist:
            messages.error(request, 'Invoice not found!')
        except Exception as e:
            messages.error(request, f'Error recording payment: {str(e)}')
    
    # Get outstanding invoices
    if invoice:
        outstanding_invoices = [invoice]
    else:
        outstanding_invoices = Invoice.objects.filter(
            status='CONFIRMED',
            balance_due__gt=0
        ).select_related('customer').order_by('-invoice_date')
    
    context = {
        'invoice': invoice,
        'outstanding_invoices': outstanding_invoices,
        'payment_methods': Payment.PAYMENT_METHOD,
        'today': timezone.now()
    }
    return render(request, 'payment_entry.html', context)


@login_required
def payments_list(request):
    """List all payments with filters"""
    payments = Payment.objects.select_related(
        'invoice', 'customer', 'created_by'
    ).order_by('-payment_date')
    
    # Filters
    search = request.GET.get('search', '')
    payment_method = request.GET.get('payment_method', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    if search:
        payments = payments.filter(
            Q(payment_id__icontains=search) |
            Q(customer__name__icontains=search) |
            Q(customer__customer_id__icontains=search) |
            Q(reference_no__icontains=search)
        )
    
    if payment_method:
        payments = payments.filter(payment_method=payment_method)
    
    if date_from:
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
        payments = payments.filter(payment_date__gte=date_from_obj)
    
    if date_to:
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
        payments = payments.filter(payment_date__lte=date_to_obj)
    
    # Summary
    total_amount = payments.aggregate(total=Sum('amount'))['total'] or 0
    
    context = {
        'payments': payments,
        'payment_methods': Payment.PAYMENT_METHOD,
        'total_amount': total_amount,
        'search': search,
        'payment_method': payment_method,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'payments_list.html', context)


@login_required
def payment_detail(request, pk):
    """View payment details"""
    payment = get_object_or_404(
        Payment.objects.select_related('invoice', 'customer', 'created_by'),
        pk=pk
    )
    
    context = {
        'payment': payment,
    }
    return render(request, 'payment_detail.html', context)


@login_required
def payment_print(request, pk):
    """A4 receipt for a payment"""
    payment = get_object_or_404(
        Payment.objects.select_related('invoice', 'customer'),
        pk=pk
    )
    company = CompanyProfile.get_company()
    invoice = payment.invoice
    # Refresh invoice from DB to get updated balance_due
    if invoice:
        from django.db import transaction
        invoice = type(invoice).objects.get(pk=invoice.pk)
    context = {
        'payment': payment,
        'invoice': invoice,
        'customer': payment.customer,
        'company': company,
        'bill_total': invoice.grand_total,
        'paid_now': payment.amount,
        'paid_total': invoice.paid_amount,
        'balance': invoice.balance_due,
    }
    return render(request, 'payment_print.html', context)


@login_required
def search_invoices(request):
    """AJAX search for invoices by number, customer name/id/phone."""
    try:
        query = request.GET.get('q', '').strip()
        invoices = Invoice.objects.filter(status='CONFIRMED', balance_due__gt=0).select_related('customer')
        if query:
            invoices = invoices.filter(
                Q(invoice_number__icontains=query) |
                Q(customer__name__icontains=query) |
                Q(customer__customer_id__icontains=query) |
                Q(customer__phone__icontains=query)
            )
        invoices = invoices.order_by('-invoice_date', '-invoice_number')[:20]
        results = []
        for inv in invoices:
            inv_date = inv.invoice_date.strftime('%d %b %Y') if inv.invoice_date else ''
            results.append({
                'id': inv.id,
                'invoice_number': inv.invoice_number,
                'customer_name': inv.customer.name,
                'customer_id': inv.customer.customer_id,
                'customer_phone': inv.customer.phone,
                'grand_total': float(inv.grand_total),
                'paid_amount': float(inv.paid_amount),
                'balance_due': float(inv.balance_due),
                'invoice_date': inv_date,
            })
        return JsonResponse({'success': True, 'invoices': results})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def settlement_history(request):
    """Customer-wise settlement history"""
    # Get all customers with outstanding or payment history
    customers = Customer.objects.annotate(
        total_sales=Coalesce(
            Sum('invoices__grand_total', filter=Q(invoices__status='CONFIRMED')),
            Decimal('0.00'),
            output_field=DecimalField()
        ),
        total_paid=Coalesce(
            Sum(
                'invoices__paid_amount',
                filter=Q(invoices__status='CONFIRMED')
            ),
            Decimal('0.00'),
            output_field=DecimalField()
        ),
        invoice_count=Count('invoices', filter=Q(invoices__status='CONFIRMED')),
        payment_count=Count('payments')
    ).filter(
        Q(total_sales__gt=0) | Q(total_paid__gt=0)
    ).order_by('-outstanding_balance')
    
    # Filters
    customer_type = request.GET.get('customer_type', '')
    search = request.GET.get('search', '')
    
    if customer_type:
        customers = customers.filter(customer_type=customer_type)
    
    if search:
        customers = customers.filter(
            Q(name__icontains=search) |
            Q(customer_id__icontains=search) |
            Q(phone__icontains=search)
        )
    
    # Summary
    summary = customers.aggregate(
        total_sales=Coalesce(Sum('invoices__grand_total', filter=Q(invoices__status='CONFIRMED')), Decimal('0.00')),
        total_outstanding=Coalesce(Sum('outstanding_balance'), Decimal('0.00')),
    )
    summary['total_collected'] = summary['total_sales'] - summary['total_outstanding']

    for customer in customers:
        if customer.total_sales and customer.total_sales > 0:
            pct = (customer.total_paid / customer.total_sales) * Decimal('100')
            customer.collection_pct = pct.quantize(
                Decimal('1'), rounding=ROUND_HALF_UP
            )
        else:
            customer.collection_pct = Decimal('0')

        # Safety clamp (never exceed 100%)
        if customer.collection_pct > 100:
            customer.collection_pct = Decimal('100')
    context = {
        'customers': customers,
        'summary': summary,
        'customer_types': Customer.CUSTOMER_TYPE_CHOICES,
        'customer_type': customer_type,
        'search': search,
    }
    return render(request, 'settlement_history.html', context)


# ==================== REPORTS ====================

@login_required
def sales_report(request):
    """Comprehensive sales report with multiple views"""
    # Default date range - last 30 days
    today = timezone.now().date()
    default_from = today - timedelta(days=30)
    
    date_from = request.GET.get('date_from', default_from.strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))
    report_type = request.GET.get('report_type', 'daily')
    customer_type = request.GET.get('customer_type', '')
    
    # Parse dates
    date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
    date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
    company = CompanyProfile.get_company()
    # Base query
    invoices = Invoice.objects.filter(
        status='CONFIRMED',
        invoice_date__date__gte=date_from_obj,
        invoice_date__date__lte=date_to_obj
    )
    
    if customer_type:
        invoices = invoices.filter(customer__customer_type=customer_type)
    
    # Overall summary
    summary = invoices.aggregate(
        total_invoices=Count('id'),
        total_sales=Coalesce(Sum('grand_total'), Decimal('0.00')),
        total_paid=Coalesce(Sum('paid_amount'), Decimal('0.00')),
        total_outstanding=Coalesce(Sum('balance_due'), Decimal('0.00')),
    )
    invoice_count = summary['total_invoices'] or 0
    summary['avg_invoice_value'] = (
        summary['total_sales'] / invoice_count if invoice_count else Decimal('0.00')
    )
    
    # Payment method breakdown
    payment_summary = Payment.objects.filter(
        invoice__in=invoices
    ).values('payment_method').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')
    
    # Report by type
    if report_type == 'daily':
        # Daily sales
        daily_sales = invoices.annotate(
            date=TruncDate('invoice_date')
        ).values('date').annotate(
            invoice_count=Count('id'),
            total_sales=Sum('grand_total'),
            total_paid=Sum('paid_amount')
        ).order_by('-date')
        
        report_data = daily_sales
        
    elif report_type == 'customer':
        # Customer-wise sales
        customer_sales = invoices.values(
            'customer__customer_id',
            'customer__name',
            'customer__customer_type'
        ).annotate(
            invoice_count=Count('id'),
            total_sales=Sum('grand_total'),
            total_paid=Sum('paid_amount'),
            total_outstanding=Sum('balance_due')
        ).order_by('-total_sales')
        
        report_data = customer_sales
        
    elif report_type == 'product':
        # Product-wise sales
        product_sales = InvoiceItem.objects.filter(
            invoice__in=invoices
        ).values(
            'product__sku',
            'product__description',
            'product__brand__name'
        ).annotate(
            total_qty=Sum('quantity'),
            total_amount=Sum('amount'),
            invoice_count=Count('invoice', distinct=True)
        ).order_by('-total_amount')
        
        report_data = product_sales
        
    else:  # monthly
        # Monthly sales
        monthly_sales = invoices.annotate(
            month=TruncMonth('invoice_date')
        ).values('month').annotate(
            invoice_count=Count('id'),
            total_sales=Sum('grand_total'),
            total_paid=Sum('paid_amount')
        ).order_by('-month')
        
        report_data = monthly_sales
    
    context = {
        'summary': summary,
        'payment_summary': payment_summary,
        'report_data': report_data,
        'report_type': report_type,
        'date_from': date_from,
        'date_to': date_to,
        'customer_type': customer_type,
        'customer_types': Customer.CUSTOMER_TYPE_CHOICES,
        'company': company,
    }
    return render(request, 'sales_report.html', context)


@login_required
def product_report(request):
    """Product performance and inventory report"""
    # Filters
    search = request.GET.get('search', '')
    brand = request.GET.get('brand', '')
    stock_status = request.GET.get('stock_status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Base query
    products = Product.objects.select_related('brand', 'supplier').annotate(
        total_sold=Coalesce(
            Sum('invoiceitem__quantity', 
                filter=Q(invoiceitem__invoice__status='CONFIRMED')),
            Decimal('0.00'),
            output_field=DecimalField()
        ),
        total_revenue=Coalesce(
            Sum('invoiceitem__amount',
                filter=Q(invoiceitem__invoice__status='CONFIRMED')),
            Decimal('0.00'),
            output_field=DecimalField()
        ),
        invoice_count=Count('invoiceitem__invoice', 
                           filter=Q(invoiceitem__invoice__status='CONFIRMED'),
                           distinct=True),
        stock_value=F('stock_qty') * F('cost_price')
    )
    
    # Apply filters
    if search:
        products = products.filter(
            Q(sku__icontains=search) |
            Q(barcode__icontains=search) |
            Q(description__icontains=search) |
            Q(fragrance_name__icontains=search)
        )
    
    if brand:
        products = products.filter(brand_id=brand)
    
    if stock_status == 'low':
        products = products.filter(stock_qty__lte=F('reorder_level'))
    elif stock_status == 'out':
        products = products.filter(stock_qty=0)
    elif stock_status == 'available':
        products = products.filter(stock_qty__gt=F('reorder_level'))
    
    # Date range for sales
    if date_from and date_to:
        date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
        date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
        
        products = products.annotate(
            period_sold=Coalesce(
                Sum('invoiceitem__quantity',
                    filter=Q(
                        invoiceitem__invoice__status='CONFIRMED',
                        invoiceitem__invoice__invoice_date__date__gte=date_from_obj,
                        invoiceitem__invoice__invoice_date__date__lte=date_to_obj
                    )),
                Decimal('0.00'),
                output_field=DecimalField()
            ),
            period_revenue=Coalesce(
                Sum('invoiceitem__amount',
                    filter=Q(
                        invoiceitem__invoice__status='CONFIRMED',
                        invoiceitem__invoice__invoice_date__date__gte=date_from_obj,
                        invoiceitem__invoice__invoice_date__date__lte=date_to_obj
                    )),
                Decimal('0.00'),
                output_field=DecimalField()
            )
        )
    
    products = products.order_by('-total_revenue')
    
    # Summary
    summary = products.aggregate(
        total_products=Count('id'),
        total_stock_value=Sum(F('stock_qty') * F('cost_price')),
        total_revenue=Sum('total_revenue'),
        low_stock_count=Count('id', filter=Q(stock_qty__lte=F('reorder_level'))),
        out_of_stock_count=Count('id', filter=Q(stock_qty=0))
    )
    
    # Get brands for filter
    from .models import Brand
    brands = Brand.objects.filter(is_active=True).order_by('name')
    
    # Top performers
    top_selling = products.order_by('-total_sold')[:10]
    top_revenue = products.order_by('-total_revenue')[:10]
    
    context = {
        'products': products,
        'summary': summary,
        'top_selling': top_selling,
        'top_revenue': top_revenue,
        'brands': brands,
        'search': search,
        'brand': brand,
        'stock_status': stock_status,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'product_report.html', context)