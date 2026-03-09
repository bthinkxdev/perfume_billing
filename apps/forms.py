from django import forms

from .models import AppConfig


CONFIG_SECTIONS = [
    ("Invoice Settings", ["invoice_prefix", "invoice_yearly_reset", "default_payment_term", "default_credit_days"]),
    ("Pricing", ["allow_price_override", "allow_negative_stock", "max_discount_percentage", "max_price_override_limit"]),
    ("Discounts", ["enable_item_level_discount", "enable_bill_level_discount"]),
    ("Customer Credit", ["enable_credit_sales", "default_credit_limit", "block_credit_if_limit_exceeded", "credit_warning_only"]),
    ("Inventory", ["low_stock_alert", "default_reorder_level", "auto_stock_deduction_on_invoice"]),
    ("Printing", ["invoice_print_size", "show_barcode_on_invoice", "show_item_number_on_invoice", "invoice_footer_text"]),
    ("Locale", ["currency_symbol", "currency_position", "timezone", "date_format"]),
    ("Operational", ["enable_activity_logs"]),
]


class AppConfigForm(forms.ModelForm):
    class Meta:
        model = AppConfig
        fields = [
            "invoice_prefix",
            "invoice_yearly_reset",
            "default_payment_term",
            "default_credit_days",
            "allow_price_override",
            "allow_negative_stock",
            "max_discount_percentage",
            "max_price_override_limit",
            "enable_item_level_discount",
            "enable_bill_level_discount",
            "enable_credit_sales",
            "default_credit_limit",
            "block_credit_if_limit_exceeded",
            "credit_warning_only",
            "low_stock_alert",
            "default_reorder_level",
            "auto_stock_deduction_on_invoice",
            "invoice_print_size",
            "show_barcode_on_invoice",
            "show_item_number_on_invoice",
            "invoice_footer_text",
            "currency_symbol",
            "currency_position",
            "timezone",
            "date_format",
            "enable_activity_logs",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({"class": "form-check-input"})
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs.update({"class": "form-control", "rows": 3})
            else:
                field.widget.attrs.update({"class": "form-control"})
