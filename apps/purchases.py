from decimal import Decimal
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from .models import Supplier, Product, PurchaseOrder, PurchaseItem, ActivityLog
from .permissions import permission_required


@login_required
@permission_required('purchase_orders.access')
def purchase_orders_list(request):
    orders = PurchaseOrder.objects.select_related('supplier', 'created_by')

    status = request.GET.get('status')
    if status:
        orders = orders.filter(status=status)

    supplier_id = request.GET.get('supplier')
    if supplier_id:
        orders = orders.filter(supplier_id=supplier_id)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        orders = orders.filter(order_date__gte=date_from)
    if date_to:
        orders = orders.filter(order_date__lte=date_to)

    orders = orders.order_by('-order_date', '-po_number')
    suppliers = Supplier.objects.filter(is_active=True) if hasattr(Supplier, 'is_active') else Supplier.objects.all()

    return render(request, 'purchase_orders_list.html', {
        'orders': orders,
        'suppliers': suppliers,
        'selected_status': status,
        'selected_supplier': supplier_id or '',
        'date_from': date_from or '',
        'date_to': date_to or '',
    })


@login_required
@permission_required('purchase_orders.access')
def purchase_order_new(request):
    suppliers = Supplier.objects.filter(is_active=True) if hasattr(Supplier, 'is_active') else Supplier.objects.all()
    products = Product.objects.filter(is_active=True).values('id', 'sku', 'description')
    today = timezone.now().date().strftime('%Y-%m-%d')
    return render(request, 'purchase_order_form.html', {
        'suppliers': suppliers,
        'products': list(products),
        'today': today,
    })


@login_required
@permission_required('purchase_orders.access', as_json=True)
@transaction.atomic
def purchase_order_save(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    try:
        supplier_id = request.POST.get('supplier')
        if not supplier_id:
            raise ValueError('Supplier is required')
        supplier = get_object_or_404(Supplier, id=supplier_id)
        order_date = request.POST.get('order_date') or timezone.now().date()
        notes = request.POST.get('notes', '')
        discount_amount = Decimal(request.POST.get('discount_amount') or 0)

        po = PurchaseOrder.objects.create(
            supplier=supplier,
            order_date=order_date,
            discount_amount=discount_amount,
            notes=notes,
            created_by=request.user,
            status='ORDERED'
        )

        product_ids = request.POST.getlist('product_id')
        quantities = request.POST.getlist('quantity')
        costs = request.POST.getlist('unit_cost')
        descriptions = request.POST.getlist('description')

        if not product_ids:
            raise ValueError('Add at least one item')

        for idx in range(len(product_ids)):
            product_id = product_ids[idx]
            qty = Decimal(quantities[idx] or 0)
            cost = Decimal(costs[idx] or 0)
            desc_val = (descriptions[idx] or '').strip() if idx < len(descriptions) else ''

            if qty <= 0:
                raise ValueError('Quantity must be greater than zero')
            if cost < 0:
                raise ValueError('Unit cost cannot be negative')

            product = None
            description = desc_val
            if product_id:
                product = get_object_or_404(Product, id=product_id)
                if not description:
                    description = product.description
            else:
                if not description:
                    raise ValueError('Description is required for custom items')

            PurchaseItem.objects.create(
                purchase_order=po,
                serial_no=idx + 1,
                product=product,
                description=description,
                quantity=qty,
                unit_cost=cost,
                amount=qty * cost
            )

        po.calculate_totals()

        ActivityLog.log_activity(
            user=request.user,
            action_type='CREATE',
            model_name='PurchaseOrder',
            object_id=po.po_number,
            description=f'Created PO {po.po_number}'
        )

        return JsonResponse({'success': True, 'po_id': po.id, 'po_number': po.po_number})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@permission_required('purchase_orders.access')
def purchase_order_detail(request, pk):
    po = get_object_or_404(PurchaseOrder.objects.select_related('supplier', 'created_by'), pk=pk)
    items = po.items.select_related('product')
    return render(request, 'purchase_order_detail.html', {
        'po': po,
        'items': items,
    })


@login_required
@permission_required('purchase_orders.access')
def purchase_order_print(request, pk):
    po = get_object_or_404(PurchaseOrder.objects.select_related('supplier'), pk=pk)
    items = po.items.select_related('product')
    return render(request, 'purchase_order_print.html', {
        'po': po,
        'items': items,
    })


@login_required
@permission_required('purchase_orders.access', as_json=True)
@transaction.atomic
def purchase_order_receive(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if po.status in ['RECEIVED', 'CANCELLED']:
        return JsonResponse({'success': False, 'error': 'PO already finalized'})
    po.receive(user=request.user)
    return JsonResponse({'success': True, 'message': 'PO marked as received and stock updated'})


@login_required
@permission_required('purchase_orders.access', as_json=True)
def quick_add_supplier(request):
    """Quick add supplier via AJAX."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        if not name:
            raise ValueError('Name is required')
        if not phone:
            raise ValueError('Phone is required')

        supplier = Supplier.objects.create(
            name=name,
            company_name=data.get('company_name', '').strip(),
            address=data.get('address', '').strip(),
            phone=phone,
            email=data.get('email', '').strip()
        )

        ActivityLog.log_activity(
            user=request.user,
            action_type='CREATE',
            model_name='Supplier',
            object_id=supplier.id,
            description=f'Quick-added supplier {supplier.name}'
        )

        return JsonResponse({
            'success': True,
            'supplier': {
                'id': supplier.id,
                'name': supplier.name,
                'company_name': supplier.company_name,
                'phone': supplier.phone,
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

