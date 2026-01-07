from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, F, Count
from django.http import JsonResponse
from django.core.paginator import Paginator
from .models import (
    Product, Brand, Supplier, StockAdjustment, 
    ActivityLog, InvoiceItem
)
from decimal import Decimal


# ==================== PRODUCTS ====================

@login_required
def products_list(request):
    """List all products with search and filters"""
    products = Product.objects.select_related('brand', 'supplier').all()
    
    # Search
    search = request.GET.get('search', '')
    if search:
        products = products.filter(
            Q(sku__icontains=search) |
            Q(barcode__icontains=search) |
            Q(fragrance_name__icontains=search) |
            Q(brand__name__icontains=search)
        )
    
    # Filters
    brand_id = request.GET.get('brand')
    if brand_id:
        products = products.filter(brand_id=brand_id)
    
    concentration = request.GET.get('concentration')
    if concentration:
        products = products.filter(concentration=concentration)
    
    status = request.GET.get('status')
    if status == 'active':
        products = products.filter(is_active=True)
    elif status == 'inactive':
        products = products.filter(is_active=False)
    elif status == 'low_stock':
        products = products.filter(stock_qty__lte=F('reorder_level'))
    
    # Low stock count (after applying filters/search)
    low_stock_count = products.filter(
        stock_qty__lte=F('reorder_level'),
        stock_qty__gt=0
    ).count()
    
    # Pagination
    paginator = Paginator(products, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get brands for filter
    brands = Brand.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'brands': brands,
        'search': search,
        'concentration_choices': Product.CONCENTRATION_CHOICES,
        'total_products': products.count(),
        'low_stock_count': low_stock_count,
    }
    return render(request, 'products_list.html', context)


@login_required
def product_create(request):
    """Create new product"""
    if request.method == 'POST':
        try:
            # Get or create brand
            brand_id = request.POST.get('brand')
            if brand_id:
                brand = Brand.objects.get(id=brand_id)
            else:
                brand_name = request.POST.get('brand_name')
                brand, _ = Brand.objects.get_or_create(name=brand_name)
            
            # Create product
            product = Product.objects.create(
                sku=request.POST.get('sku'),
                barcode=request.POST.get('barcode') or None,
                brand=brand,
                fragrance_name=request.POST.get('fragrance_name'),
                concentration=request.POST.get('concentration'),
                size_ml=Decimal(request.POST.get('size_ml')),
                cost_price=Decimal(request.POST.get('cost_price')),
                wholesale_price=Decimal(request.POST.get('wholesale_price')),
                retail_price=Decimal(request.POST.get('retail_price')),
                stock_qty=Decimal(request.POST.get('stock_qty', 0)),
                reorder_level=Decimal(request.POST.get('reorder_level', 0)),
                batch_no=request.POST.get('batch_no', ''),
            )
            
            # Optional supplier
            supplier_id = request.POST.get('supplier')
            if supplier_id:
                product.supplier_id = supplier_id
                product.save()
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='CREATE',
                model_name='Product',
                object_id=product.id,
                description=f"Created product: {product.sku} - {product.fragrance_name}",
                request=request
            )
            
            messages.success(request, f'Product {product.sku} created successfully!')
            return redirect('apps:products_list')
            
        except Exception as e:
            messages.error(request, f'Error creating product: {str(e)}')
    
    brands = Brand.objects.filter(is_active=True).order_by('name')
    suppliers = Supplier.objects.filter(is_active=True).order_by('name')
    
    context = {
        'brands': brands,
        'suppliers': suppliers,
        'concentration_choices': Product.CONCENTRATION_CHOICES,
    }
    return render(request, 'product_form.html', context)


@login_required
def product_edit(request, pk):
    """Edit existing product"""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        try:
            # Get or create brand
            brand_id = request.POST.get('brand')
            if brand_id:
                brand = Brand.objects.get(id=brand_id)
            else:
                brand_name = request.POST.get('brand_name')
                brand, _ = Brand.objects.get_or_create(name=brand_name)
            
            # Update product
            product.sku = request.POST.get('sku')
            product.barcode = request.POST.get('barcode') or None
            product.brand = brand
            product.fragrance_name = request.POST.get('fragrance_name')
            product.concentration = request.POST.get('concentration')
            product.size_ml = Decimal(request.POST.get('size_ml'))
            product.cost_price = Decimal(request.POST.get('cost_price'))
            product.wholesale_price = Decimal(request.POST.get('wholesale_price'))
            product.retail_price = Decimal(request.POST.get('retail_price'))
            product.reorder_level = Decimal(request.POST.get('reorder_level', 0))
            product.batch_no = request.POST.get('batch_no', '')
            
            supplier_id = request.POST.get('supplier')
            product.supplier_id = supplier_id if supplier_id else None
            
            product.save()
            
            # Log activity
            ActivityLog.log_activity(
                user=request.user,
                action_type='UPDATE',
                model_name='Product',
                object_id=product.id,
                description=f"Updated product: {product.sku}",
                request=request
            )
            
            messages.success(request, f'Product {product.sku} updated successfully!')
            return redirect('apps:products_list')
            
        except Exception as e:
            messages.error(request, f'Error updating product: {str(e)}')
    
    brands = Brand.objects.filter(is_active=True).order_by('name')
    suppliers = Supplier.objects.filter(is_active=True).order_by('name')
    
    context = {
        'product': product,
        'brands': brands,
        'suppliers': suppliers,
        'concentration_choices': Product.CONCENTRATION_CHOICES,
        'is_edit': True,
    }
    return render(request, 'product_form.html', context)


@login_required
def product_delete(request, pk):
    """Delete product (soft delete by marking inactive)"""
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        product.is_active = False
        product.save()
        
        ActivityLog.log_activity(
            user=request.user,
            action_type='DELETE',
            model_name='Product',
            object_id=product.id,
            description=f"Deactivated product: {product.sku}",
            request=request
        )
        
        messages.success(request, f'Product {product.sku} deactivated successfully!')
        return redirect('apps:products_list')
    
    return render(request, 'product_delete.html', {'product': product})


@login_required
def product_detail(request, pk):
    """View product details with stock history"""
    product = get_object_or_404(Product.objects.select_related('brand', 'supplier'), pk=pk)
    
    # Get stock adjustments
    adjustments = product.adjustments.select_related('created_by').order_by('-created_at')[:10]
    
    # Get sales history
    sales = InvoiceItem.objects.filter(
        product=product,
        invoice__status='CONFIRMED'
    ).select_related('invoice', 'invoice__customer').order_by('-created_at')[:10]
    
    # Calculate stats
    total_sold = InvoiceItem.objects.filter(
        product=product,
        invoice__status='CONFIRMED'
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    context = {
        'product': product,
        'adjustments': adjustments,
        'sales': sales,
        'total_sold': total_sold,
    }
    return render(request, 'product_detail.html', context)


# ==================== STOCK / INVENTORY ====================

@login_required
def inventory_list(request):
    """Stock overview with filters"""
    products = Product.objects.select_related('brand', 'supplier').filter(is_active=True)
    
    # Search
    search = request.GET.get('search', '')
    if search:
        products = products.filter(
            Q(sku__icontains=search) |
            Q(barcode__icontains=search) |
            Q(fragrance_name__icontains=search) |
            Q(brand__name__icontains=search)
        )
    
    # Stock status filter
    stock_status = request.GET.get('stock_status')
    if stock_status == 'low':
        products = products.filter(stock_qty__lte=F('reorder_level'), stock_qty__gt=0)
    elif stock_status == 'out':
        products = products.filter(stock_qty=0)
    elif stock_status == 'available':
        products = products.filter(stock_qty__gt=F('reorder_level'))
    
    # Brand filter
    brand_id = request.GET.get('brand')
    if brand_id:
        products = products.filter(brand_id=brand_id)
    
    # Calculate stock value
    products = products.annotate(
        stock_value=F('stock_qty') * F('cost_price')
    )
    
    # Pagination
    paginator = Paginator(products, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Stock summary
    summary = products.aggregate(
        total_items=Sum('stock_qty'),
        total_value=Sum(F('stock_qty') * F('cost_price')),
        low_stock_count=Sum(
            1, filter=Q(stock_qty__lte=F('reorder_level'), stock_qty__gt=0)
        ),
        out_of_stock_count=Sum(1, filter=Q(stock_qty=0))
    )
    
    brands = Brand.objects.filter(is_active=True).order_by('name')
    
    context = {
        'page_obj': page_obj,
        'brands': brands,
        'search': search,
        'summary': summary,
    }
    return render(request, 'inventory_list.html', context)


@login_required
def stock_adjustment(request):
    """Stock adjustment form"""
    if request.method == 'POST':
        try:
            product_id = request.POST.get('product')
            product = Product.objects.get(id=product_id)
            
            adjustment = StockAdjustment.objects.create(
                product=product,
                adjustment_type=request.POST.get('adjustment_type'),
                quantity=Decimal(request.POST.get('quantity')),
                reason=request.POST.get('reason', '') or '',
                reference_no=request.POST.get('reference_no', ''),
                created_by=request.user
            )
            
            ActivityLog.log_activity(
                user=request.user,
                action_type='CREATE',
                model_name='StockAdjustment',
                object_id=adjustment.id,
                description=f"Stock adjustment: {adjustment.adjustment_type} {adjustment.quantity} units of {product.sku}",
                request=request
            )
            
            messages.success(request, f'Stock adjusted successfully! New stock: {product.stock_qty}')
            return redirect('apps:inventory_list')
            
        except Exception as e:
            messages.error(request, f'Error adjusting stock: {str(e)}')
    
    products = Product.objects.filter(is_active=True).select_related('brand').order_by('brand__name', 'fragrance_name')
    
    context = {
        'products': products,
        'adjustment_types': StockAdjustment.ADJUSTMENT_TYPE,
    }
    return render(request, 'stock_adjustment_form.html', context)


@login_required
def stock_history(request):
    """View all stock adjustments"""
    adjustments = StockAdjustment.objects.select_related(
        'product', 'product__brand', 'created_by'
    ).order_by('-created_at')
    
    # Filters
    product_id = request.GET.get('product')
    if product_id:
        adjustments = adjustments.filter(product_id=product_id)
    
    adjustment_type = request.GET.get('adjustment_type')
    if adjustment_type:
        adjustments = adjustments.filter(adjustment_type=adjustment_type)
    
    # Pagination
    paginator = Paginator(adjustments, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    products = Product.objects.filter(is_active=True).order_by('sku')
    
    context = {
        'page_obj': page_obj,
        'products': products,
        'adjustment_types': StockAdjustment.ADJUSTMENT_TYPE,
    }
    return render(request, 'stock_history.html', context)


# ==================== AJAX ENDPOINTS ====================

@login_required
def ajax_product_search(request):
    """AJAX endpoint for product search (for billing)"""
    search = request.GET.get('q', '')
    
    products = Product.objects.filter(
        Q(sku__icontains=search) |
        Q(barcode__icontains=search) |
        Q(fragrance_name__icontains=search),
        is_active=True,
        stock_qty__gt=0
    ).select_related('brand')[:10]
    
    results = [{
        'id': p.id,
        'sku': p.sku,
        'barcode': p.barcode or '',
        'description': p.description,
        'stock_qty': float(p.stock_qty),
        'wholesale_price': float(p.wholesale_price),
        'retail_price': float(p.retail_price),
    } for p in products]
    
    return JsonResponse({'results': results})


@login_required
def ajax_product_by_barcode(request):
    """Get product details by barcode"""
    barcode = request.GET.get('barcode', '')
    
    try:
        product = Product.objects.select_related('brand').get(
            barcode=barcode,
            is_active=True
        )
        
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'sku': product.sku,
                'barcode': product.barcode,
                'description': product.description,
                'stock_qty': float(product.stock_qty),
                'wholesale_price': float(product.wholesale_price),
                'retail_price': float(product.retail_price),
            }
        })
    except Product.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Product not found'
        })


# ==================== BRANDS ====================

@login_required
def brands_list(request):
    """List all brands"""
    brands = Brand.objects.annotate(
        product_count=Count('products')
    ).order_by('name')
    
    context = {'brands': brands}
    return render(request, 'brands_list.html', context)


@login_required
def brand_create(request):
    """Create new brand - AJAX"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        
        brand, created = Brand.objects.get_or_create(
            name=name,
            defaults={'description': description}
        )
        
        if created:
            return JsonResponse({
                'success': True,
                'brand': {'id': brand.id, 'name': brand.name}
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Brand already exists'
            })
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})