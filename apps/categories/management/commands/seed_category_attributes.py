import django.core.management.base
from django.db import transaction
from apps.categories.models import Categories, CategoryAttribute
from apps.products.models import Attribute, AttributeValue


ATTRIBUTES_DATA = {
    'Taille': {
        'code': 'size',
        'values': [
            {'value': 'XS', 'code': 'xs'},
            {'value': 'S', 'code': 's'},
            {'value': 'M', 'code': 'm'},
            {'value': 'L', 'code': 'l'},
            {'value': 'XL', 'code': 'xl'},
            {'value': 'XXL', 'code': 'xxl'},
        ],
    },
    'Couleur': {
        'code': 'color',
        'values': [
            {'value': 'Noir', 'code': 'black', 'hex_color': '#000000'},
            {'value': 'Blanc', 'code': 'white', 'hex_color': '#FFFFFF'},
            {'value': 'Rouge', 'code': 'red', 'hex_color': '#FF0000'},
            {'value': 'Bleu', 'code': 'blue', 'hex_color': '#0000FF'},
            {'value': 'Vert', 'code': 'green', 'hex_color': '#00FF00'},
            {'value': 'Jaune', 'code': 'yellow', 'hex_color': '#FFFF00'},
            {'value': 'Gris', 'code': 'gray', 'hex_color': '#808080'},
            {'value': 'Rose', 'code': 'pink', 'hex_color': '#FFC0CB'},
            {'value': 'Marron', 'code': 'brown', 'hex_color': '#8B4513'},
            {'value': 'Beige', 'code': 'beige', 'hex_color': '#F5F5DC'},
        ],
    },
    'Matiere': {
        'code': 'material',
        'values': [
            {'value': 'Coton', 'code': 'cotton'},
            {'value': 'Polyester', 'code': 'polyester'},
            {'value': 'Lin', 'code': 'linen'},
            {'value': 'Soie', 'code': 'silk'},
            {'value': 'Cuir', 'code': 'leather'},
            {'value': 'Jean', 'code': 'denim'},
        ],
    },
    'Pointure': {
        'code': 'shoe_size',
        'values': [
            {'value': '36', 'code': '36'},
            {'value': '37', 'code': '37'},
            {'value': '38', 'code': '38'},
            {'value': '39', 'code': '39'},
            {'value': '40', 'code': '40'},
            {'value': '41', 'code': '41'},
            {'value': '42', 'code': '42'},
            {'value': '43', 'code': '43'},
            {'value': '44', 'code': '44'},
            {'value': '45', 'code': '45'},
            {'value': '46', 'code': '46'},
        ],
    },
    'Memoire': {
        'code': 'memory',
        'values': [
            {'value': '32 Go', 'code': '32gb'},
            {'value': '64 Go', 'code': '64gb'},
            {'value': '128 Go', 'code': '128gb'},
            {'value': '256 Go', 'code': '256gb'},
            {'value': '512 Go', 'code': '512gb'},
            {'value': '1 To', 'code': '1tb'},
        ],
    },
    'Taille ecran': {
        'code': 'screen_size',
        'values': [
            {'value': '5"', 'code': '5inch'},
            {'value': '5.5"', 'code': '5_5inch'},
            {'value': '6"', 'code': '6inch'},
            {'value': '6.5"', 'code': '6_5inch'},
            {'value': '7"', 'code': '7inch'},
        ],
    },
    'Stockage': {
        'code': 'storage',
        'values': [
            {'value': '256 Mo', 'code': '256mb'},
            {'value': '512 Mo', 'code': '512mb'},
            {'value': '1 Go', 'code': '1gb'},
            {'value': '2 Go', 'code': '2gb'},
            {'value': '4 Go', 'code': '4gb'},
            {'value': '8 Go', 'code': '8gb'},
        ],
    },
    'Capacite': {
        'code': 'capacity',
        'values': [
            {'value': '500 ml', 'code': '500ml'},
            {'value': '1 L', 'code': '1l'},
            {'value': '1.5 L', 'code': '1_5l'},
            {'value': '2 L', 'code': '2l'},
            {'value': '5 L', 'code': '5l'},
        ],
    },
    'Version': {
        'code': 'version',
        'values': [
            {'value': 'Standard', 'code': 'standard'},
            {'value': 'Pro', 'code': 'pro'},
            {'value': 'Premium', 'code': 'premium'},
            {'value': 'Mini', 'code': 'mini'},
        ],
    },
    'Voltage': {
        'code': 'voltage',
        'values': [
            {'value': '110V', 'code': '110v'},
            {'value': '220V', 'code': '220v'},
            {'value': 'Multi', 'code': 'multi'},
        ],
    },
}

CATEGORY_ATTRIBUTE_MAP = {
    'vetement': ['size', 'color', 'material'],
    'vetements': ['size', 'color', 'material'],
    'vetements': ['size', 'color', 'material'],
    't-shirt': ['size', 'color', 'material'],
    'tshirts': ['size', 'color', 'material'],
    'pantalon': ['size', 'color', 'material'],
    'robe': ['size', 'color', 'material'],
    'chaussure': ['shoe_size', 'color'],
    'chaussures': ['shoe_size', 'color'],
    'electronique': ['memory', 'screen_size', 'color'],
    'electroniques': ['memory', 'screen_size', 'color'],
    'telephone': ['memory', 'screen_size', 'color'],
    'telephones': ['memory', 'screen_size', 'color'],
    'smartphone': ['memory', 'screen_size', 'color'],
    'smartphones': ['memory', 'screen_size', 'color'],
    'tablette': ['memory', 'screen_size', 'color'],
    'tablettes': ['memory', 'screen_size', 'color'],
    'ordinateur': ['memory', 'storage', 'color'],
    'ordinateurs': ['memory', 'storage', 'color'],
    'maison': ['color', 'material', 'capacity'],
    'cuisine': ['color', 'material', 'capacity'],
    'salon': ['color', 'material'],
    'beaute': ['color', 'version'],
    'cosmétique': ['color', 'version'],
    'alimentation': ['capacity', 'version'],
    'alimentaire': ['capacity', 'version'],
}


class Command(django.core.management.base.BaseCommand):
    help = 'Seed attributes, attribute values, and category-attribute links'

    def handle(self, *args, **options):
        created_attrs = 0
        created_values = 0
        created_links = 0

        with transaction.atomic():
            for attr_name, attr_data in ATTRIBUTES_DATA.items():
                attr, created = Attribute.objects.get_or_create(
                    code=attr_data['code'],
                    defaults={'name': attr_name, 'is_variant': True},
                )
                if created:
                    created_attrs += 1
                    self.stdout.write(f'  + Attribute: {attr_name} ({attr_data["code"]})')

                for val_data in attr_data['values']:
                    _, created = AttributeValue.objects.get_or_create(
                        attribute=attr,
                        value=val_data['value'],
                        defaults={
                            'code': val_data['code'],
                            'hex_color': val_data.get('hex_color'),
                            'is_active': True,
                        },
                    )
                    if created:
                        created_values += 1

            categories = Categories.objects.filter(category_type='product')
            for cat in categories:
                cat_slug = cat.slug.lower()
                matching_codes = set()
                for pattern, codes in CATEGORY_ATTRIBUTE_MAP.items():
                    if pattern in cat_slug or cat_slug in pattern:
                        matching_codes.update(codes)

                if not matching_codes:
                    continue

                attrs = Attribute.objects.filter(code__in=matching_codes)
                for attr in attrs:
                    _, created = CategoryAttribute.objects.get_or_create(
                        category=cat,
                        attribute=attr,
                    )
                    if created:
                        created_links += 1
                        self.stdout.write(f'  + Link: {cat.name} <-> {attr.name}')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! {created_attrs} attributes, '
            f'{created_values} values, {created_links} category-attribute links created.'
        ))
