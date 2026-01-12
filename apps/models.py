from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid


class CompanyProfile(models.Model):
    """Single instance company header configuration"""
    company_name_en = models.CharField(max_length=255)
    company_name_ar = models.CharField(max_length=255, blank=True, null=True)
    logo = models.ImageField(upload_to='company/', blank=True, null=True)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    address_line3 = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20)
    fax = models.CharField(max_length=20, blank=True)
    mobile = models.CharField(max_length=20)
    email = models.EmailField()
    trn_number = models.CharField(max_length=50, blank=True, verbose_name="TRN/Registration No")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Profile"
        verbose_name_plural = "Company Profile"

    def __str__(self):
        return self.company_name_en

    # @classmethod
    # def get_company(cls):
    #     """Get or create single company instance"""
    #     return cls.objects.first() or cls.objects.create(
    #         company_name_en="Default Company",
    #         address_line1="Address",
    #         phone="000000",
    #         mobile="000000",
    #         email="info@company.com"
    #     )
    @classmethod
    def get_company(cls):
        """Get or create single company instance"""
        company = cls.objects.first()
        if company:
            return company

        return cls.objects.create(
            company_name_en="WAFEEN GENERAL TRADING EST",
            company_name_ar="مؤسسة وافين للتجارة العامة",
            logo="loggo.jpeg",
            address_line1="Al Mubarak Building - 2nd Floor, Office No: 3",
            address_line2="Jleeb Al Shyouk, P.O Box: 92356",
            address_line3="Al Firdous, Kuwait - 40090",
            phone="24332064",
            fax="24342062",
            mobile="+96597691984",
            email="afsal@wafeen.com",
            trn_number=""
        )


class Customer(models.Model):
    CUSTOMER_TYPE_CHOICES = [
        ('WHOLESALE', 'Wholesale'),
        ('RETAIL', 'Retail'),
    ]
    
    customer_id = models.CharField(max_length=20, unique=True, editable=False)
    customer_type = models.CharField(max_length=10, choices=CUSTOMER_TYPE_CHOICES, default='WHOLESALE')
    name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, db_index=True,unique=True)
    email = models.EmailField(blank=True)
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Default invoice discount percentage for this customer"
    )
    
    # Credit management
    credit_limit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    outstanding_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone']),
            models.Index(fields=['customer_id']),
        ]

    def __str__(self):
        return f"{self.customer_id} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.customer_id:
            self.customer_id = self.generate_customer_id()
        super().save(*args, **kwargs)

    def generate_customer_id(self):
        """Generate unique customer ID"""
        prefix = 'WC' if self.customer_type == 'WHOLESALE' else 'RC'
        last_customer = Customer.objects.filter(
            customer_id__startswith=prefix
        ).order_by('-customer_id').first()
        
        if last_customer:
            last_num = int(last_customer.customer_id[2:])
            new_num = last_num + 1
        else:
            new_num = 1
        
        return f"{prefix}{new_num:06d}"

    def get_available_credit(self):
        """Calculate available credit"""
        return self.credit_limit - self.outstanding_balance

    def can_take_credit(self, amount):
        """Check if customer can take credit for given amount"""
        if self.customer_type != 'WHOLESALE':
            return False
        return self.get_available_credit() >= amount


class Supplier(models.Model):
    """Supplier master for purchase management"""
    supplier_id = models.CharField(max_length=20, unique=True, editable=False)
    name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    
    outstanding_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.supplier_id} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.supplier_id:
            self.supplier_id = self.generate_supplier_id()
        super().save(*args, **kwargs)

    def generate_supplier_id(self):
        """Generate unique supplier ID"""
        last_supplier = Supplier.objects.order_by('-supplier_id').first()
        if last_supplier:
            last_num = int(last_supplier.supplier_id[3:])
            new_num = last_num + 1
        else:
            new_num = 1
        return f"SUP{new_num:06d}"


class Brand(models.Model):
    """Perfume brand master"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    """Perfume product master"""
    CONCENTRATION_CHOICES = [
        ('ATTAR', 'Attar'),
        ('EDP', 'Eau De Parfum'),
        ('EDT', 'Eau De Toilette'),
        ('OIL', 'Perfume Oil'),
        ('COLOGNE', 'Cologne'),
        ('OTHER', 'Other'),
    ]
    
    # Product identification
    sku = models.CharField(max_length=50, unique=True, verbose_name="Item No/SKU")
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True, db_index=True)
    
    # Product details
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name='products')
    fragrance_name = models.CharField(max_length=255)
    concentration = models.CharField(max_length=20, choices=CONCENTRATION_CHOICES)
    size_ml = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Size (ml)")
    
    # Description for invoice
    description = models.CharField(max_length=500, help_text="Display name on invoice")
    
    # Pricing
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    retail_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    
    # Inventory
    stock_qty = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Additional fields
    batch_no = models.CharField(max_length=50, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True)
    purchase_date = models.DateField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['brand', 'fragrance_name', 'size_ml']
        indexes = [
            models.Index(fields=['barcode']),
            models.Index(fields=['sku']),
        ]

    def __str__(self):
        return f"{self.sku} - {self.get_full_name()}"

    def get_full_name(self):
        """Get complete product name"""
        return f"{self.brand.name} {self.fragrance_name} {self.concentration} {self.size_ml}ml"

    def save(self, *args, **kwargs):
        if not self.description:
            self.description = self.get_full_name()
        super().save(*args, **kwargs)

    def is_low_stock(self):
        """Check if product is low on stock"""
        return self.stock_qty <= self.reorder_level

    def get_default_price(self, customer_type='WHOLESALE'):
        """Get default price based on customer type"""
        if customer_type == 'WHOLESALE':
            return self.wholesale_price
        return self.retail_price


class Invoice(models.Model):
    PAYMENT_TERMS = [
        ('CASH', 'Cash'),
        ('CREDIT', 'Credit'),
    ]
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    # Invoice identification
    invoice_number = models.CharField(max_length=20, unique=True, editable=False, db_index=True)
    invoice_date = models.DateTimeField(default=timezone.now)
    
    # Customer
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    
    # Payment terms
    payment_terms = models.CharField(max_length=10, choices=PAYMENT_TERMS, default='CASH')
    
    # Amounts
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Status
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    
    # Tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='invoices_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices_cancelled')

    class Meta:
        ordering = ['-invoice_number']
        indexes = [
            models.Index(fields=['invoice_date']),
            models.Index(fields=['customer', 'invoice_date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        super().save(*args, **kwargs)

    def generate_invoice_number(self):
        """Generate sequential invoice number"""
        current_year = timezone.now().year
        prefix = f"INV{current_year}"
        
        last_invoice = Invoice.objects.filter(
            invoice_number__startswith=prefix
        ).order_by('-invoice_number').first()
        
        if last_invoice:
            last_num = int(last_invoice.invoice_number.split('-')[1])
            new_num = last_num + 1
        else:
            new_num = 1
        
        return f"{prefix}-{new_num:06d}"

    def calculate_totals(self):
        """Calculate invoice totals from line items"""
        items = self.items.all()
        self.subtotal = sum(item.amount for item in items)
        self.grand_total = self.subtotal - self.discount_amount
        self.balance_due = self.grand_total - self.paid_amount
        self.save()

    def confirm_invoice(self, user):
        """Confirm invoice and update inventory"""
        if self.status != 'DRAFT':
            return False
        
        # Deduct stock
        for item in self.items.all():
            product = item.product
            product.stock_qty -= item.quantity
            product.save()
        
        # Update customer balance if credit
        if self.payment_terms in ['CREDIT', 'PARTIAL'] and self.balance_due > 0:
            self.customer.outstanding_balance += self.balance_due
            self.customer.save()
        
        self.status = 'CONFIRMED'
        self.confirmed_at = timezone.now()
        self.save()
        return True

    def cancel_invoice(self, user):
        """Cancel invoice and restore inventory"""
        if self.status != 'CONFIRMED':
            return False
        
        # Restore stock
        for item in self.items.all():
            product = item.product
            product.stock_qty += item.quantity
            product.save()
        
        # Update customer balance
        if self.payment_terms in ['CREDIT', 'PARTIAL'] and self.balance_due > 0:
            self.customer.outstanding_balance -= self.balance_due
            self.customer.save()
        
        self.status = 'CANCELLED'
        self.cancelled_at = timezone.now()
        self.cancelled_by = user
        self.save()
        return True

    def is_overdue(self):
        """Check if invoice payment is overdue (30 days)"""
        if self.status != 'CONFIRMED' or self.balance_due <= 0:
            return False
        from datetime import timedelta
        due_date = self.invoice_date + timedelta(days=30)
        return timezone.now() > due_date


class InvoiceItem(models.Model):
    """Invoice line items"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    serial_no = models.PositiveIntegerField()
    
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    barcode = models.CharField(max_length=100, blank=True)
    item_no = models.CharField(max_length=50)
    description = models.CharField(max_length=500)
    
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Price override tracking
    is_price_overridden = models.BooleanField(default=False)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['serial_no']
        unique_together = ['invoice', 'serial_no']

    def __str__(self):
        return f"{self.invoice.invoice_number} - Item {self.serial_no}"

    def save(self, *args, **kwargs):
        # Auto-calculate amount
        self.amount = self.quantity * self.unit_price
        
        # Store original price if overridden
        if self.pk is None:  # New item
            default_price = self.product.get_default_price(self.invoice.customer.customer_type)
            if self.unit_price != default_price:
                self.is_price_overridden = True
                self.original_price = default_price
        
        super().save(*args, **kwargs)


class PriceOverrideLog(models.Model):
    """Log all price overrides for audit"""
    invoice_item = models.ForeignKey(InvoiceItem, on_delete=models.CASCADE, related_name='override_logs')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    overridden_price = models.DecimalField(max_digits=10, decimal_places=2)
    difference = models.DecimalField(max_digits=10, decimal_places=2)
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Override on {self.invoice_item.invoice.invoice_number}"

    def save(self, *args, **kwargs):
        self.difference = self.overridden_price - self.original_price
        super().save(*args, **kwargs)


class Payment(models.Model):
    """Payment entries for invoices"""
    PAYMENT_METHOD = [
        ('CASH', 'Cash'),
        ('CARD', 'Card'),
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CHEQUE', 'Cheque'),
        ('OTHER', 'Other'),
    ]
    
    payment_id = models.CharField(max_length=20, unique=True, editable=False)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='payments')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='payments')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    payment_date = models.DateTimeField(default=timezone.now)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD, default='CASH')
    
    reference_no = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment {self.payment_id} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.payment_id:
            self.payment_id = self.generate_payment_id()
        
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new:
            # Update invoice paid amount and balance
            self.invoice.paid_amount += self.amount
            self.invoice.balance_due = self.invoice.grand_total - self.invoice.paid_amount
            self.invoice.save()
            
            # Update customer outstanding
            self.customer.outstanding_balance -= self.amount
            self.customer.save()

    def generate_payment_id(self):
        """Generate unique payment ID"""
        prefix = f"PAY{timezone.now().year}"
        last_payment = Payment.objects.filter(
            payment_id__startswith=prefix
        ).order_by('-payment_id').first()
        
        if last_payment:
            last_num = int(last_payment.payment_id.split('-')[1])
            new_num = last_num + 1
        else:
            new_num = 1
        
        return f"{prefix}-{new_num:06d}"


class StockAdjustment(models.Model):
    """Manual stock adjustments"""
    ADJUSTMENT_TYPE = [
        ('ADD', 'Add Stock'),
        ('REMOVE', 'Remove Stock'),
        ('CORRECTION', 'Correction'),
    ]
    
    adjustment_id = models.CharField(max_length=20, unique=True, editable=False)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='adjustments')
    
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    
    reason = models.TextField(blank=True)
    reference_no = models.CharField(max_length=100, blank=True)
    
    previous_qty = models.DecimalField(max_digits=10, decimal_places=2)
    new_qty = models.DecimalField(max_digits=10, decimal_places=2)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.adjustment_id} - {self.product.sku}"

    def save(self, *args, **kwargs):
        if not self.adjustment_id:
            self.adjustment_id = self.generate_adjustment_id()
        
        is_new = self.pk is None
        if is_new:
            self.previous_qty = self.product.stock_qty
            
            if self.adjustment_type == 'ADD':
                self.new_qty = self.previous_qty + self.quantity
            else:
                self.new_qty = self.previous_qty - self.quantity
            
            super().save(*args, **kwargs)
            
            # Update product stock
            self.product.stock_qty = self.new_qty
            self.product.save()
        else:
            super().save(*args, **kwargs)

    def generate_adjustment_id(self):
        """Generate unique adjustment ID"""
        prefix = "ADJ"
        last_adj = StockAdjustment.objects.order_by('-adjustment_id').first()
        
        if last_adj:
            last_num = int(last_adj.adjustment_id[3:])
            new_num = last_num + 1
        else:
            new_num = 1
        
        return f"{prefix}{new_num:06d}"


class SystemSettings(models.Model):
    """Global system settings"""
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Setting"
        verbose_name_plural = "System Settings"

    def __str__(self):
        return self.key

    @classmethod
    def get_setting(cls, key, default=None):
        """Get setting value"""
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set_setting(cls, key, value, user=None):
        """Set setting value"""
        setting, created = cls.objects.get_or_create(key=key)
        setting.value = str(value)
        setting.updated_by = user
        setting.save()
        return setting


class ActivityLog(models.Model):
    """Track user activities for audit"""
    ACTION_TYPES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('PRINT', 'Print'),
        ('CANCEL', 'Cancel'),
        ('PRICE_OVERRIDE', 'Price Override'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    description = models.TextField()
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['model_name', 'object_id']),
        ]

    def __str__(self):
        return f"{self.user} - {self.action_type} - {self.model_name}"

    @classmethod
    def log_activity(cls, user, action_type, model_name, object_id, description, request=None):
        """Create activity log entry"""
        log = cls(
            user=user,
            action_type=action_type,
            model_name=model_name,
            object_id=str(object_id),
            description=description
        )
        
        if request:
            log.ip_address = cls.get_client_ip(request)
            log.user_agent = request.META.get('HTTP_USER_AGENT', '')
        
        log.save()
        return log

    @staticmethod
    def get_client_ip(request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


# ==================== PURCHASE ORDERS ====================

class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ORDERED', 'Ordered'),
        ('RECEIVED', 'Received'),
        ('CANCELLED', 'Cancelled'),
    ]

    po_number = models.CharField(max_length=20, unique=True, editable=False, db_index=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    order_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ORDERED')

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='purchase_orders_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-order_date', '-po_number']
        indexes = [
            models.Index(fields=['po_number']),
            models.Index(fields=['order_date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"PO {self.po_number}"

    def save(self, *args, **kwargs):
        if not self.po_number:
            self.po_number = self.generate_po_number()
        super().save(*args, **kwargs)

    def generate_po_number(self):
        """Generate sequential PO number per year."""
        current_year = timezone.now().year
        prefix = f"PO{current_year}"
        last_po = PurchaseOrder.objects.filter(po_number__startswith=prefix).order_by('-po_number').first()
        if last_po:
            last_num = int(last_po.po_number.split('-')[1])
            new_num = last_num + 1
        else:
            new_num = 1
        return f"{prefix}-{new_num:06d}"

    def calculate_totals(self):
        items = self.items.all()
        self.subtotal = sum(item.amount for item in items)
        self.grand_total = self.subtotal - self.discount_amount
        self.save(update_fields=['subtotal', 'grand_total'])

    def receive(self, user=None):
        """Mark as received and update inventory."""
        if self.status == 'RECEIVED' or self.status == 'CANCELLED':
            return False
        for item in self.items.all():
            product = item.product
            product.stock_qty += item.quantity
            product.save()
        self.status = 'RECEIVED'
        self.received_at = timezone.now()
        self.save(update_fields=['status', 'received_at'])
        if user:
            ActivityLog.log_activity(
                user=user,
                action_type='UPDATE',
                model_name='PurchaseOrder',
                object_id=self.po_number,
                description=f'Received PO {self.po_number}'
            )
        return True


class PurchaseItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    serial_no = models.PositiveIntegerField()
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True)
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['serial_no']
        unique_together = ['purchase_order', 'serial_no']

    def __str__(self):
        return f"{self.purchase_order.po_number} - Item {self.serial_no}"

    def save(self, *args, **kwargs):
        self.amount = self.quantity * self.unit_cost
        super().save(*args, **kwargs)