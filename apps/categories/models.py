from django.db import models
from mptt.models import MPTTModel, TreeForeignKey
from mptt.managers import TreeManager

# Create your models here.


class Categories(MPTTModel):
    CATEGORY_TYPE_CHOICES = [
        ('product', 'Produit'),
        ('shop', 'Boutique'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to="images/category", blank=True, null=True)
    icon_name = models.CharField(max_length=100, blank=True, null=True, help_text="Nom de l'icône Lucide (ex: ShoppingBag, Store)")
    icon_color = models.CharField(max_length=7, blank=True, null=True, help_text="Code hexa de la couleur (ex: #FF5733)")
    bg_icon = models.CharField(max_length=7, blank=True, null=True, help_text="Code hexa de la couleur (ex: #FF5733)")
    badge = models.CharField(max_length=100, blank=True, null=True, help_text="Tendance")
    badge_color = models.CharField(max_length=20, blank=True, null=True, help_text="bg du badge (ex: bg-orange-500")
    parent_category = TreeForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children'
    )
    fields_config = models.JSONField(
        default=list, 
        blank=True,
        help_text="Format: [{'name': 'ram', 'label': 'Mémoire RAM', 'type': 'number'}, ...]"
    )
    tree = TreeManager()
    is_active = models.BooleanField(default=True)
    category_type = models.CharField(max_length=10, choices=CATEGORY_TYPE_CHOICES, default="product")

    class MPTTMeta:
        parent_attr = 'parent_category' 
        order_insertion_by = ['name']
        verbose_name_plural = "Categories"
        
    def validate_product_data(self, data):
        """
        data est le dictionnaire envoyé par le front.
        On vérifie si toutes les clés obligatoires de 'field_definitions' sont là.
        """
        for field in self.field_definitions:
            if field['required'] and field['name'] not in data:
                raise ValueError(f"Le champ {field['name']} est obligatoire.")
        return True
    
    def is_leaf_node(self):
        return self.get_descendant_count() == 0

    def __str__(self):
        type_label = "Produit" if self.category_type == "product" else "Boutique"
        return f"{self.name} ({type_label})"


class CategoryAttribute(models.Model):

    FIELD_TYPES = [
        ('text', 'Texte'),
        ('number', 'Nombre'),
        ('boolean', 'Booléen'),
        ('choice', 'Choix'),
        ('multichoice', 'Choix multiple'),
        ('date', 'Date'),
        ('datetime', 'Date et heure'),
        ('textarea', 'Zone de texte'),
        # etc.
    ]
        
    category = models.ForeignKey(Categories, on_delete=models.CASCADE)
    attribute = models.ForeignKey('products.Attribute', on_delete=models.CASCADE)
    required = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.attribute.name} for {self.category.name}"


