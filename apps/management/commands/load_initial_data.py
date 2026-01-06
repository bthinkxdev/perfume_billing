from django.core.management.base import BaseCommand
from apps.models import CompanyProfile, Brand

class Command(BaseCommand):
    help = 'Load initial data for the system'

    def handle(self, *args, **kwargs):
        # Create company profile
        if not CompanyProfile.objects.exists():
            CompanyProfile.objects.create(
                company_name_en="Your Perfume Trading Co.",
                address_line1="123 Business Street",
                phone="1234567890",
                mobile="0987654321",
                email="info@perfumetrading.com"
            )
            self.stdout.write(self.style.SUCCESS('Company profile created'))
        
        # Create some brands
        brands = ['Ajmal', 'Rasasi', 'Al Haramain', 'Swiss Arabian', 'Lattafa']
        for brand_name in brands:
            Brand.objects.get_or_create(name=brand_name)
        
        self.stdout.write(self.style.SUCCESS(f'Created {len(brands)} brands'))


# python manage.py load_initial_data