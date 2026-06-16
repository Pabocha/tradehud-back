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
    
    parent_category = TreeForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children'
    )
    tree = TreeManager()

    is_active = models.BooleanField(default=True)
    category_type = models.CharField(max_length=10, choices=CATEGORY_TYPE_CHOICES, default="product")

    class MPTTMeta:
        parent_attr = 'parent_category'  # 👈 ceci règle l'erreur
        order_insertion_by = ['name']


    def __str__(self):
        type_label = "Produit" if self.category_type == "product" else "Boutique"
        return f"{self.name} ({type_label})"

class CategoryField(models.Model):
    FIELD_TYPES = [
        ('text', 'Texte'),
        ('number', 'Nombre'),
        ('boolean', 'Booléen'),
        ('choice', 'Choix'),
        ('multichoice', 'Choix multiple'),
        ('date', 'Date'),
        ('datetime', 'Date et heure'),
        ('textarea', 'Zone de texte'),
        ('color', 'Couleur'),
        # etc.
    ]


    category = models.ForeignKey("Categories", related_name="fields", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    label = models.CharField(max_length=255)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    required = models.BooleanField(default=False)
    choices = models.JSONField(blank=True, null=True)  # Pour les champs de type "choice"

    def __str__(self):
        return f"{self.name} ({self.field_type})"

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
    attribute = models.ForeignKey('apps.products.Attribute', on_delete=models.CASCADE)
    required = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.attribute.name} for {self.category.name}"


