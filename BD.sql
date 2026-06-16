CREATE TABLE Products(
    CHOICES_STATUS = [
        ('disponible', 'Disponible'),
        ('rupture', 'En rupture'),
        ('precommande', 'Pre-commande'), 
    ]
    id_product INTEGER PRIMARY KEY AUTOINCREMENT,
    name_product VARCHAR(255) NOT NULL,
    price_product DECIMAL(10,2) NOT NULL,
    description_product TEXT,
    user FOREIGN KEY (id_user) REFERENCES Users(id_user) ON DELETE CASCADE,
    date_added DATETIME NOT NULL,
    categorie FOREIGN KEY (id_categorie) REFERENCES Categories(id_categorie) ON DELETE SET NULL,
    image_product IMAGE,
    quantite_stock INTEGER,
    galerie_images FOREIGN KEY (id_image) REFERENCES Galeries(id_image) ON DELETE SET NULL,
    status_product VARCHAR(255, choices=CHOICES_STATUS),
    poids FLOAT,
    dimension VARCHAR(255),
    remise DECIMAL(10, 2)
    frais_livraison DECIMAL(10, 2)
    nombre_avis INTEGER,
)

CREATE TABLE Commandes(

    CHOICES_STATUS = [
        ('attente', 'En attente'),
        ('traitemant', 'En traitement'),
        ('expediee', 'Expédiée'),
        ('livre', 'Livrée'),
        ('annuler', 'Annuler')
    ]
    CHOICES_PAYEMENT = [
        ('livraison', 'A la livraison'),
        ('carte_bancaire', 'Carte bancaire'),
        ('virement_bancaire', 'Virement bancaire'),
        ('wave', 'Wave'),
        ('om', 'Orange money'),
        ('mtn', 'MTN money'),
        ('airtel', 'Airtel money'),
        ('djamo', 'Djamo'),
    ]

    id_commande INTEGER PRIMARY KEY AUTOINCREMENT,
    products FOREIGN KEY (id_product) REFERENCES Products(id_product) ON DELETE CASCADE,
    client FOREIGN KEY (id_user) REFERENCES Users(id_user) ON DELETE CASCADE,
    date_commande DATETIME NOT NULL,
    frais_livraison DECIMAL(10,0),
    addresse_livraison TEXT,
    latitude FLOAT,
    longitude FLOAT,
    status_commande VARCHAR(255, choices=CHOICES_STATUS, default='attente'),
    moyen_payement VARCHAR(255, choices=CHOICES_PAYEMENT, default='livraison')
    payement_confirme BOOLEAN(default=false),
    date_expedition DATETIME,
    date_livraison_estime DATETIME,
)

CREATE TABLE LigneCommandes(
    id_ligne_command INTEGER PRIMARY KEY AUTOINCREMENT,
    commande FOREIGN KEY (id_commande) REFERENCES Commandes(id_commande) ON DELETE CASCADE,
    product FOREIGN KEY (id_product) REFERENCES Products(id_product) ON DELETE CASCADE,
    quantity INTEGER(default=1),
    prix_unitaire DECIMAL(10, 2),

    -- def total_produit(self):
    --     return self.quantite * self.prix_unitaire

    -- def __str__(self):
    --     return f"{self.quantite} x {self.produit.nom} (Commande {self.commande.numero_commande})"
)

CREATE TABLE Users(

    CHOICES_USER = [
        ('client', 'Client'),
        ('vendeur', 'Vendeur'),
        ('administrateur', 'Administrateur'),
    ]
    id_user INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    number_phone VARCHAR(255) NOT NULL,
    type_user VARCHAR(255, choices=CHOICES_USER, default='client')
    latitude DECIMAL(10, 2),
    longitude DECIMAL(10, 2),
)

CREATE TABLE Contacts(
    id_contact INTEGER PRIMARY KEY AUTOINCREMENT,
)