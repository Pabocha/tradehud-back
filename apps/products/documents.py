# documents.py

from django_elasticsearch_dsl import Document, Index, fields
from django_elasticsearch_dsl.registries import registry
from .models import Products

# Crée un index nommé "products"
product_index = Index('products')

# Paramètres de l'index (facultatif mais utile)
product_index.settings(
    number_of_shards=1,
    number_of_replicas=0
)
@registry.register_document
class ProductDocument(Document):
    name_suggest = fields.CompletionField()
    tags = fields.KeywordField(multi=True)
    tags_text = fields.TextField()  # ✅ champ nécessaire pour la recherche

    class Index:
        name = 'products'

    class Django:
        model = Products
        fields = [
            'id',
            'name',
            'description',
            'image',
        ]

    def prepare_name_suggest(self, instance):
        inputs = [instance.name] + list(instance.tags.names())
        return {
            "input": inputs,
            "weight": 10
        }

    def prepare_tags(self, instance):
        return list(instance.tags.names())

    def prepare_tags_text(self, instance):  # ✅ nécessaire pour le champ `tags_text`
        return " ".join(tag.lower() for tag in instance.tags.names())

    
    
