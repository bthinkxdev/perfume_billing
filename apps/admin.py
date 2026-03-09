from django.contrib import admin
from .models import (
    CompanyProfile, Customer, Supplier, Brand, Product,
    Invoice, InvoiceItem, Payment, StockAdjustment,
    PriceOverrideLog, AppConfig, ActivityLog
)


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ['company_name_en', 'phone', 'email']
    
    def has_add_permission(self, request):
        # Only allow one company profile
        return not CompanyProfile.objects.exists()


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['customer_id', 'name', 'phone', 'customer_type', 'outstanding_balance', 'is_active']
    list_filter = ['customer_type', 'is_active']
    search_fields = ['customer_id', 'name', 'phone']


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['supplier_id', 'name', 'phone', 'outstanding_balance', 'is_active']
    search_fields = ['supplier_id', 'name', 'phone']


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']
    search_fields = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'brand', 'fragrance_name', 'concentration', 'size_ml', 
                    'wholesale_price', 'stock_qty', 'is_active']
    list_filter = ['brand', 'concentration', 'is_active']
    search_fields = ['sku', 'barcode', 'fragrance_name']


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ['amount']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'invoice_date', 'customer', 'grand_total', 
                    'payment_terms', 'status', 'balance_due']
    list_filter = ['status', 'payment_terms', 'invoice_date']
    search_fields = ['invoice_number', 'customer__name']
    readonly_fields = ['invoice_number']
    inlines = [InvoiceItemInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_id', 'invoice', 'customer', 'amount', 
                    'payment_date', 'payment_method']
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['payment_id', 'invoice__invoice_number']


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ['adjustment_id', 'product', 'adjustment_type', 
                    'quantity', 'previous_qty', 'new_qty', 'created_at']
    list_filter = ['adjustment_type', 'created_at']
    search_fields = ['adjustment_id', 'product__sku']


@admin.register(PriceOverrideLog)
class PriceOverrideLogAdmin(admin.ModelAdmin):
    list_display = ['invoice_item', 'product', 'customer', 'original_price', 
                    'overridden_price', 'difference', 'timestamp']
    list_filter = ['timestamp']
    readonly_fields = ['timestamp', 'difference']


@admin.register(AppConfig)
class AppConfigAdmin(admin.ModelAdmin):
    list_display = ['id', 'invoice_prefix', 'default_payment_term', 'timezone', 'updated_at']

    def has_add_permission(self, request):
        return not AppConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action_type', 'model_name', 'object_id', 'timestamp']
    list_filter = ['action_type', 'model_name', 'timestamp']
    search_fields = ['description', 'object_id']
    readonly_fields = ['timestamp']