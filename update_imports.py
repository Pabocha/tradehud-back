#!/usr/bin/env python3
"""
Script to update all imports from old app locations to new app structure
Old: panier, commentaires, contacts, produits, boutique, categories, restaurant
New: apps/client/{panier,commentaires,contacts}, apps/vendor/{produits,boutique,categories,restaurant}
"""

import os
import re
from pathlib import Path

# Map of old import paths to new ones
IMPORT_MAPPINGS = {
    # Client imports
    'from panier.': 'from apps.client.panier.',
    'from commentaires.': 'from apps.client.commentaires.',
    'from contacts.': 'from apps.client.contacts.',
    # Vendor imports  
    'from produits.': 'from apps.vendor.produits.',
    'from boutique.': 'from apps.vendor.boutique.',
    'from categories.': 'from apps.vendor.categories.',
    'from restaurant.': 'from apps.vendor.restaurant.',
    # String references in ForeignKey/etc
    "'panier.": "'apps.client.panier.",
    "'commentaires.": "'apps.client.commentaires.",
    "'contacts.": "'apps.client.contacts.",
    "'produits.": "'apps.vendor.produits.",
    "'boutique.": "'apps.vendor.boutique.",
    "'categories.": "'apps.vendor.categories.",
    "'restaurant.": "'apps.vendor.restaurant.",
}

PROJECT_ROOT = Path('e:\\projet_perso\\Ecommerce')

# Directories to scan
SCAN_DIRS = [
    'apps/client',
    'apps/vendor',
    'comptes',
    'ecom_app',
    'commandes',
    'chat',
]

def update_file(file_path):
    """Update imports in a single file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Apply all mappings
        for old, new in IMPORT_MAPPINGS.items():
            content = content.replace(old, new)
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, file_path
        return False, file_path
    except Exception as e:
        return None, f"{file_path}: {str(e)}"

def main():
    updated_files = []
    unchanged_files = []
    error_files = []
    
    for dir_name in SCAN_DIRS:
        dir_path = PROJECT_ROOT / dir_name
        if not dir_path.exists():
            print(f"⚠️  Directory not found: {dir_path}")
            continue
        
        print(f"📂 Scanning {dir_name}...")
        
        for py_file in dir_path.rglob('*.py'):
            # Skip migrations and __pycache__
            if 'migrations' in str(py_file) or '__pycache__' in str(py_file):
                continue
            
            result, path_info = update_file(str(py_file))
            if result is True:
                updated_files.append(path_info)
                print(f"  ✅ Updated: {py_file.name}")
            elif result is False:
                unchanged_files.append(path_info)
            else:
                error_files.append(path_info)
                print(f"  ❌ Error: {path_info}")
    
    print("\n" + "="*60)
    print(f"✅ Updated: {len(updated_files)} files")
    print(f"⏭️  Unchanged: {len(unchanged_files)} files")
    print(f"❌ Errors: {len(error_files)} files")
    
    if updated_files:
        print("\nUpdated files:")
        for f in updated_files:
            rel_path = Path(f).relative_to(PROJECT_ROOT)
            print(f"  - {rel_path}")
    
    if error_files:
        print("\nErrors:")
        for e in error_files:
            print(f"  - {e}")

if __name__ == '__main__':
    main()
