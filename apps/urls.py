# apps/urls.py

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import products
from . import purchases
from . import customer
from . import payments
from django.conf import settings
from django.conf.urls.static import static
app_name = 'apps'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    
    # Authentication
    path('login/', auth_views.LoginView.as_view(template_name="registration/login.html"), name='login'),
    # Authentication
    path('logout/', views.user_logout, name='logout'),
    
    # New Bill
    path('bill/new/', views.new_bill, name='new_bill'),
    path('bill/save/', views.save_invoice, name='save_invoice'),
    
    # AJAX endpoints
    path('api/search-product/', views.search_product, name='search_product'),
    path('api/search-customer/', views.search_customer, name='search_customer'),
    path('api/quick-add-customer/', views.quick_add_customer, name='quick_add_customer'),
    
    # Invoices
    path('invoices/', views.invoices_list, name='invoices_list'),
    path('invoices/<int:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:invoice_id>/print/', views.invoice_print, name='invoice_print'),
    path('invoices/<int:invoice_id>/cancel/', views.cancel_invoice, name='cancel_invoice'),
    path('invoices/<int:invoice_id>/confirm/',views.confirm_draft_invoice, name='confirm_draft_invoice'),

        # Products
    path('products/', products.products_list, name='products_list'),
    path('products/create/', products.product_create, name='product_create'),
    path('products/<int:pk>/edit/', products.product_edit, name='product_edit'),
    path('products/<int:pk>/delete/', products.product_delete, name='product_delete'),
    path('products/<int:pk>/', products.product_detail, name='product_detail'),
    
    # Inventory / Stock
    path('inventory/', products.inventory_list, name='inventory_list'),
    path('inventory/adjust/', products.stock_adjustment, name='stock_adjustment'),
    path('inventory/history/', products.stock_history, name='stock_history'),

    # Purchase Orders (Local PO)
    path('purchase-orders/', purchases.purchase_orders_list, name='purchase_orders_list'),
    path('purchase-orders/new/', purchases.purchase_order_new, name='purchase_order_new'),
    path('purchase-orders/save/', purchases.purchase_order_save, name='purchase_order_save'),
    path('purchase-orders/<int:pk>/', purchases.purchase_order_detail, name='purchase_order_detail'),
    path('purchase-orders/<int:pk>/print/', purchases.purchase_order_print, name='purchase_order_print'),
    path('purchase-orders/<int:pk>/receive/', purchases.purchase_order_receive, name='purchase_order_receive'),
    path('api/quick-add-supplier/', purchases.quick_add_supplier, name='quick_add_supplier'),
    
    # Brands
    path('brands/', products.brands_list, name='brands_list'),
    path('brands/create/', products.brand_create, name='brand_create'),
    
    # AJAX Endpoints
    path('ajax/product-search/', products.ajax_product_search, name='ajax_product_search'),
    path('ajax/product-barcode/', products.ajax_product_by_barcode, name='ajax_product_by_barcode'),


        # Customers
    path('customers/', customer.customers_list, name='customers_list'),
    path('customers/create/', customer.customer_create, name='customer_create'),
    path('customers/<int:pk>/edit/', customer.customer_edit, name='customer_edit'),
    path('customers/<int:pk>/delete/', customer.customer_delete, name='customer_delete'),
    path('customers/<int:pk>/', customer.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/statement/', customer.customer_statement, name='customer_statement'),
    path('customers/<int:pk>/statement/print/', customer.customer_statement_print, name='customer_statement_print'),
    
    # Customer Ledger
    path('customer-ledger/', customer.customer_ledger, name='customer_ledger'),
    path('customer-ledger/<int:pk>/', customer.customer_ledger, name='customer_ledger_detail'),
    
    # Outstanding
    path('outstanding/', customer.outstanding_list, name='outstanding_list'),
    path('outstanding/<int:pk>/', customer.outstanding_detail, name='outstanding_detail'),
    
    # Payments
    path('payment/entry/', payments.payment_entry, name='payment_entry'),
    path('payment/entry/<int:invoice_id>/', payments.payment_entry, name='payment_entry_invoice'),
    path('payments/', payments.payments_list, name='payments_list'),
    path('payments/history/', payments.settlement_history, name='settlement_history'),
    path('payment/<int:pk>/', payments.payment_detail, name='payment_detail'),
    path('payment/<int:pk>/print/', payments.payment_print, name='payment_print'),
    path('api/search-invoices/', payments.search_invoices, name='search_invoices'),
    
    # Reports
    path('reports/sales/', payments.sales_report, name='sales_report'),
    path('reports/product/', payments.product_report, name='product_report'),
    
    
    # AJAX Endpoints
    path('ajax/customer-search/', customer.ajax_customer_search, name='ajax_customer_search'),
    path('ajax/customer-phone/', customer.ajax_customer_by_phone, name='ajax_customer_by_phone'),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
