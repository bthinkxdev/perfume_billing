from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count, F, DecimalField
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from django.db.models import Min
from .models import (
    Customer, Invoice, Payment, InvoiceItem, 
    ActivityLog, Product
)


# ==================== CUSTOMERS ====================

@login_required
def customers_list(request):
    """List all customers with search and filters"""
    customers = Customer.objects.annotate(
        total_invoices=Count('invoices', filter=Q(invoices__status='CONFIRMED')),
        total_sales=Coalesce(
            Sum('invoices__grand_total', filter=Q(invoices__status='CONFIRMED')),
            Decimal('0.00'),
            output_field=DecimalField()
        ),
        total_paid=Coalesce(
            Sum('invoices__paid_amount', filter=Q(invoices__status='CONFIRMED')),
            Decimal('0.00'),
            output_field=DecimalField()
        )
    )
    
    # Search
    search = request.GET.get('search', '')
    if search:
        customers = customers.filter(
            Q(customer_id__icontains=search) |
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(company_name__icontains=search) |
            Q(email__icontains=search)
        )
    
    # Filters
    customer_type = request.GET.get('type')
    if customer_type:
        customers = customers.filter(customer_type=customer_type)
    
    status = request.GET.get('status')
    if status == 'active':
        customers = customers.filter(is_active=True)
    elif status == 'inactive':
        customers = customers.filter(is_active=False)
    elif status == 'credit':
        customers = customers.filter(outstanding_balance__gt=0)
    
    # Sorting
    sort_by = request.GET.get('sort', '-created_at')
    customers = customers.order_by(sort_by)
    
    # Pagination
    paginator = Paginator(customers, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Summary statistics
    summary = Customer.objects.filter(is_active=True).aggregate(
        total_customers=Count('id'),
        wholesale_count=Count('id', filter=Q(customer_type='WHOLESALE')),
        retail_count=Count('id', filter=Q(customer_type='RETAIL')),
        total_outstanding=Coalesce(Sum('outstanding_balance'), Decimal('0.00'))
    )
    
    context = {
        'page_obj': page_obj,
        'search': search,
        'summary': summary,
        'customer_types': Customer.CUSTOMER_TYPE_CHOICES,
    }
    return render(request, 'customers_list.html', context)


@login_required
def customer_create(request):
    """Create new customer"""
    if request.method == 'POST':
        try:
            customer = Customer.objects.create(
                customer_type=request.POST.get('customer_type'),
                name=request.POST.get('name'),
                company_name=request.POST.get('company_name', ''),
                address=request.POST.get('address', ''),
                phone=request.POST.get('phone'),
                email=request.POST.get('email', ''),
                credit_limit=Decimal(request.POST.get('credit_limit', 0))
            )
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='CREATE',
                model_name='Customer',
                object_id=customer.id,
                description=f"Created customer: {customer.customer_id} - {customer.name}",
                request=request
            )
            
            messages.success(request, f'Customer {customer.customer_id} created successfully!')
            return redirect('apps:customers_list')
            
        except Exception as e:
            messages.error(request, f'Error creating customer: {str(e)}')
    
    context = {
        'customer_types': Customer.CUSTOMER_TYPE_CHOICES,
    }
    return render(request, 'customer_form.html', context)


@login_required
def customer_edit(request, pk):
    """Edit existing customer"""
    customer = get_object_or_404(Customer, pk=pk)
    
    if request.method == 'POST':
        try:
            customer.customer_type = request.POST.get('customer_type')
            customer.name = request.POST.get('name')
            customer.company_name = request.POST.get('company_name', '')
            customer.address = request.POST.get('address', '')
            customer.phone = request.POST.get('phone')
            customer.email = request.POST.get('email', '')
            customer.credit_limit = Decimal(request.POST.get('credit_limit', 0))
            customer.is_active = request.POST.get('is_active') == 'on'
            customer.save()
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='UPDATE',
                model_name='Customer',
                object_id=customer.id,
                description=f"Updated customer: {customer.customer_id}",
                request=request
            )
            
            messages.success(request, f'Customer {customer.customer_id} updated successfully!')
            return redirect('apps:customer_detail', pk=customer.id)
            
        except Exception as e:
            messages.error(request, f'Error updating customer: {str(e)}')
    
    context = {
        'customer': customer,
        'customer_types': Customer.CUSTOMER_TYPE_CHOICES,
        'is_edit': True,
    }
    return render(request, 'customer_form.html', context)


@login_required
def customer_detail(request, pk):
    """View customer details with complete transaction history"""
    customer = get_object_or_404(
        Customer.objects.annotate(
            total_invoices=Count('invoices', filter=Q(invoices__status='CONFIRMED')),
            total_sales=Coalesce(
                Sum('invoices__grand_total', filter=Q(invoices__status='CONFIRMED')),
                Decimal('0.00'),
                output_field=DecimalField()
            ),
            total_paid=Coalesce(
                Sum('payments__amount'),
                Decimal('0.00'),
                output_field=DecimalField()
            )
        ),
        pk=pk
    )
    
    # Recent invoices
    invoices = customer.invoices.filter(
        status='CONFIRMED'
    ).order_by('-invoice_date')[:10]
    
    # Recent payments
    payments = customer.payments.select_related(
        'invoice', 'created_by'
    ).order_by('-payment_date')[:10]
    
    # Credit history - Outstanding invoices
    outstanding_invoices = customer.invoices.filter(
        status='CONFIRMED',
        balance_due__gt=0
    ).order_by('invoice_date')
    
    # Top products purchased
    top_products = InvoiceItem.objects.filter(
        invoice__customer=customer,
        invoice__status='CONFIRMED'
    ).values(
        'product__sku',
        'product__fragrance_name',
        'product__brand__name'
    ).annotate(
        total_qty=Sum('quantity'),
        total_amount=Sum('amount')
    ).order_by('-total_amount')[:5]
    
    # Calculate days since last purchase
    last_invoice = customer.invoices.filter(status='CONFIRMED').order_by('-invoice_date').first()
    days_since_purchase = None
    if last_invoice:
        days_since_purchase = (timezone.now() - last_invoice.invoice_date).days
    
    context = {
        'customer': customer,
        'invoices': invoices,
        'payments': payments,
        'outstanding_invoices': outstanding_invoices,
        'top_products': top_products,
        'days_since_purchase': days_since_purchase,
    }
    return render(request, 'customer_detail.html', context)


@login_required
def customer_delete(request, pk):
    """Delete customer (soft delete)"""
    customer = get_object_or_404(Customer, pk=pk)
    
    # Check if customer has outstanding balance
    if customer.outstanding_balance > 0:
        messages.error(request, 'Cannot delete customer with outstanding balance!')
        return redirect('apps:customer_detail', pk=customer.id)
    
    if request.method == 'POST':
        customer.is_active = False
        customer.save()
        
        ActivityLog.log_activity(
            user=request.user,
            action_type='DELETE',
            model_name='Customer',
            object_id=customer.id,
            description=f"Deactivated customer: {customer.customer_id}",
            request=request
        )
        
        messages.success(request, f'Customer {customer.customer_id} deactivated successfully!')
        return redirect('apps:customers_list')
    
    return render(request, 'customer_delete.html', {'customer': customer})


# ==================== CUSTOMER LEDGER ====================

@login_required
def customer_ledger(request, pk=None):
    """Customer ledger showing all transactions"""
    
    # If specific customer
    if pk:
        customer = get_object_or_404(Customer, pk=pk)
        customers = [customer]
    else:
        # All customers or filtered
        customers_qs = Customer.objects.filter(is_active=True)
        
        search = request.GET.get('search', '')
        if search:
            customers_qs = customers_qs.filter(
                Q(customer_id__icontains=search) |
                Q(name__icontains=search) |
                Q(phone__icontains=search)
            )
        
        customer_id = request.GET.get('customer')
        if customer_id:
            customers_qs = customers_qs.filter(id=customer_id)
        
        customers = list(customers_qs)
    
    # Date range filter
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    ledger_entries = []
    
    for customer in customers:
        # Get invoices
        invoices = customer.invoices.filter(status='CONFIRMED')
        if date_from:
            invoices = invoices.filter(invoice_date__gte=date_from)
        if date_to:
            invoices = invoices.filter(invoice_date__lte=date_to)
        
        # Get payments
        payments = customer.payments.all()
        if date_from:
            payments = payments.filter(payment_date__gte=date_from)
        if date_to:
            payments = payments.filter(payment_date__lte=date_to)
        
        # Combine and sort by date
        for invoice in invoices:
            ledger_entries.append({
                'customer': customer,
                'date': invoice.invoice_date,
                'type': 'INVOICE',
                'reference': invoice.invoice_number,
                'description': f'Invoice - {invoice.payment_terms}',
                'debit': invoice.grand_total,
                'credit': Decimal('0.00'),
                'balance': None,  # Will calculate
                'invoice': invoice,
            })
        
        for payment in payments:
            ledger_entries.append({
                'customer': customer,
                'date': payment.payment_date,
                'type': 'PAYMENT',
                'reference': payment.payment_id,
                'description': f'Payment - {payment.get_payment_method_display()}',
                'debit': Decimal('0.00'),
                'credit': payment.amount,
                'balance': None,  # Will calculate
                'payment': payment,
            })
    
    # Sort by date
    ledger_entries.sort(key=lambda x: x['date'])
    
    # Calculate running balance per customer
    customer_balances = {}
    for entry in ledger_entries:
        cust_id = entry['customer'].id
        if cust_id not in customer_balances:
            customer_balances[cust_id] = Decimal('0.00')
        
        customer_balances[cust_id] += entry['debit'] - entry['credit']
        entry['balance'] = customer_balances[cust_id]
    
    # Pagination
    paginator = Paginator(ledger_entries, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Summary
    total_debit = sum(e['debit'] for e in ledger_entries)
    total_credit = sum(e['credit'] for e in ledger_entries)
    net_balance = total_debit - total_credit
    
    # Get all customers for filter
    all_customers = Customer.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'customer': customer if pk else None,
        'all_customers': all_customers,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'net_balance': net_balance,
    }
    return render(request, 'customer_ledger.html', context)


# ==================== OUTSTANDING ====================

@login_required
def outstanding_list(request):
    """List all customers with outstanding balance"""
    customers = Customer.objects.filter(
        is_active=True,
        outstanding_balance__gt=0
    ).annotate(
        total_invoices=Count('invoices', filter=Q(invoices__status='CONFIRMED', invoices__balance_due__gt=0)),
        oldest_invoice_date=Min('invoices__invoice_date', filter=Q(invoices__status='CONFIRMED', invoices__balance_due__gt=0))
    )
    
    # Search
    search = request.GET.get('search', '')
    if search:
        customers = customers.filter(
            Q(customer_id__icontains=search) |
            Q(name__icontains=search) |
            Q(phone__icontains=search)
        )
    
    # Filter by aging
    aging = request.GET.get('aging')
    if aging == '0-30':
        cutoff_date = timezone.now() - timedelta(days=30)
        customers = customers.filter(oldest_invoice_date__gte=cutoff_date)
    elif aging == '31-60':
        start_date = timezone.now() - timedelta(days=60)
        end_date = timezone.now() - timedelta(days=31)
        customers = customers.filter(oldest_invoice_date__gte=start_date, oldest_invoice_date__lte=end_date)
    elif aging == '61-90':
        start_date = timezone.now() - timedelta(days=90)
        end_date = timezone.now() - timedelta(days=61)
        customers = customers.filter(oldest_invoice_date__gte=start_date, oldest_invoice_date__lte=end_date)
    elif aging == '90+':
        cutoff_date = timezone.now() - timedelta(days=90)
        customers = customers.filter(oldest_invoice_date__lt=cutoff_date)
    
    # Sorting
    sort_by = request.GET.get('sort', '-outstanding_balance')
    customers = customers.order_by(sort_by)
    
    # Calculate aging for each customer
    for customer in customers:
        if customer.oldest_invoice_date:
            days_old = (timezone.now() - customer.oldest_invoice_date).days
            customer.days_outstanding = days_old
            
            # Categorize aging
            if days_old <= 30:
                customer.aging_category = '0-30'
                customer.aging_class = 'success'
            elif days_old <= 60:
                customer.aging_category = '31-60'
                customer.aging_class = 'warning'
            elif days_old <= 90:
                customer.aging_category = '61-90'
                customer.aging_class = 'danger'
            else:
                customer.aging_category = '90+'
                customer.aging_class = 'dark'
        else:
            customer.days_outstanding = 0
            customer.aging_category = 'N/A'
            customer.aging_class = 'secondary'
    
    # Pagination
    paginator = Paginator(customers, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Summary statistics
    summary = Customer.objects.filter(is_active=True, outstanding_balance__gt=0).aggregate(
        total_outstanding=Coalesce(Sum('outstanding_balance'), Decimal('0.00')),
        total_customers=Count('id')
    )
    
    # Aging summary (use template-safe keys without hyphens)
    aging_key_map = {
        '0-30': 'range_0_30',
        '31-60': 'range_31_60',
        '61-90': 'range_61_90',
        '90+': 'range_90_plus',
    }
    aging_summary = {v: Decimal('0.00') for v in aging_key_map.values()}
    
    for customer in customers:
        category = getattr(customer, 'aging_category', None)
        key = aging_key_map.get(category)
        if key:
            aging_summary[key] += customer.outstanding_balance
    
    context = {
        'page_obj': page_obj,
        'search': search,
        'summary': summary,
        'aging_summary': aging_summary,
    }
    return render(request, 'outstanding_list.html', context)


@login_required
def outstanding_detail(request, pk):
    """Detailed outstanding report for a customer"""
    customer = get_object_or_404(Customer, pk=pk)
    
    # Get all unpaid/partially paid invoices
    outstanding_invoices = customer.invoices.filter(
        status='CONFIRMED',
        balance_due__gt=0
    ).order_by('invoice_date')
    
    # Calculate aging for each invoice
    for invoice in outstanding_invoices:
        days_old = (timezone.now() - invoice.invoice_date).days
        invoice.days_outstanding = days_old
        
        if days_old <= 30:
            invoice.aging_category = '0-30 days'
            invoice.aging_class = 'success'
        elif days_old <= 60:
            invoice.aging_category = '31-60 days'
            invoice.aging_class = 'warning'
        elif days_old <= 90:
            invoice.aging_category = '61-90 days'
            invoice.aging_class = 'danger'
        else:
            invoice.aging_category = '90+ days'
            invoice.aging_class = 'dark'
    
    # Payment history for this customer
    payments = customer.payments.select_related('invoice').order_by('-payment_date')[:10]
    
    context = {
        'customer': customer,
        'outstanding_invoices': outstanding_invoices,
        'payments': payments,
    }
    return render(request, 'outstanding_detail.html', context)


# ==================== PAYMENTS ====================

@login_required
def payment_entry(request, invoice_id=None):
    """Record payment against invoice or customer"""
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
            return redirect('apps:customer_detail', pk=invoice.customer.id)
            
        except Invoice.DoesNotExist:
            messages.error(request, 'Invoice not found!')
        except Exception as e:
            messages.error(request, f'Error recording payment: {str(e)}')
    
    # Get outstanding invoices for customer selection
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
    }
    return render(request, 'payment_entry.html', context)


# ==================== AJAX ENDPOINTS ====================

@login_required
def ajax_customer_search(request):
    """AJAX endpoint for customer search"""
    search = request.GET.get('q', '')
    
    customers = Customer.objects.filter(
        Q(customer_id__icontains=search) |
        Q(name__icontains=search) |
        Q(phone__icontains=search) |
        Q(company_name__icontains=search),
        is_active=True
    )[:10]
    
    results = [{
        'id': c.id,
        'customer_id': c.customer_id,
        'name': c.name,
        'company_name': c.company_name,
        'phone': c.phone,
        'customer_type': c.customer_type,
        'outstanding_balance': float(c.outstanding_balance),
        'credit_limit': float(c.credit_limit),
        'available_credit': float(c.get_available_credit()),
    } for c in customers]
    
    return JsonResponse({'results': results})


@login_required
def ajax_customer_by_phone(request):
    """Get customer details by phone"""
    phone = request.GET.get('phone', '')
    
    try:
        customer = Customer.objects.get(phone=phone, is_active=True)
        
        return JsonResponse({
            'success': True,
            'customer': {
                'id': customer.id,
                'customer_id': customer.customer_id,
                'name': customer.name,
                'company_name': customer.company_name,
                'phone': customer.phone,
                'email': customer.email,
                'address': customer.address,
                'customer_type': customer.customer_type,
                'outstanding_balance': float(customer.outstanding_balance),
                'credit_limit': float(customer.credit_limit),
                'available_credit': float(customer.get_available_credit()),
            }
        })
    except Customer.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Customer not found'
        })
    except Customer.MultipleObjectsReturned:
        return JsonResponse({
            'success': False,
            'error': 'Multiple customers found with this phone number'
        })

