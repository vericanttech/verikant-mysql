# Vitrine marketing & remise globale (MVP)

This document describes the first version of the public **vitrine** page, **QR code** on invoices, **checkout remise** (global discount %), and **visit analytics**.

## Features

### 1. Remise globale au point de vente

- Dans le modal de paiement (PDV), cochez **Remise globale (%)** et saisissez un pourcentage (ex. 10 pour 10 %).
- Le calcul est : **sous-total HT des lignes → remise → HT net → TVA sur HT net → TTC** (même logique que la TVA appliquée sur le montant HT après remise).
- Les factures enregistrent `discount_rate` (fraction 0–1), `discount_amount` et un `amount_ht` **net** après remise.
- Les impressions (A4, thermique, Bluetooth) et la fiche facture affichent **sous-total HT**, **remise** et **HT net / TVA / TTC** lorsque la remise est utilisée.

### 2. Page publique `/v/<shop_id>` (toujours « live »)

- URL **unique** par magasin : `/v/<id>` (clé primaire). **Tant que le magasin est actif** (`is_active`), la page est accessible — pas de bascule « activer la vitrine » pour l’URL.
- **Contenu minimal** : logo (profil), nom, adresse, téléphones du profil, texte d’accueil optionnel, bandeau **remise globale** optionnel.
- **Produits** : seuls les articles ajoutés dans **Administration → Vitrine & promos** apparaissent (table `vitrine_product_selections`). Le reste du stock n’est pas listé automatiquement. Par ligne : ordre, badges **Promo** et **Nouveauté** (cartes publiques séparées), retrait de la vitrine. Les articles sans aucun badge sont regroupés sous **« À la une »** sur la page publique.
- Sans produits ni remise globale, le client voit surtout **infos + logo** (page toujours utile pour QR / lien).
- Anciens liens `/v/ancien-slug` : redirection **301** vers `/v/<id>` si un slug historique existe.
- La remise affichée est **indépendante** de la caisse : le caissier applique la remise réelle au PDV.
- **noindex** par défaut.

### 3. QR code sur la facture

- Pour tout magasin **actif**, les impressions **standard** et **thermique** incluent un **QR code** vers `PUBLIC_BASE_URL/v/<shop_id>`.
- L’URL utilisée pour le QR est basée sur **`PUBLIC_BASE_URL`** (recommandé en production). Sans cette variable, l’URL du serveur courant (`request.url_root`) est utilisée (utile en local, moins stable en prod derrière proxy).

### 4. Analytics (7 jours)

- Chaque chargement de la page vitrine enregistre une ligne dans `vitrine_visits` avec un **identifiant visiteur** stocké en cookie (`vitrine_vid`, longue durée).
- L’écran **Administration → Vitrine & promos** affiche :
  - le nombre de **visites** sur 7 jours ;
  - le nombre de **visiteurs uniques** (distincts par cookie) sur 7 jours.

## Configuration administrateur

1. Connectez-vous avec un compte **admin**.
2. Ouvrez **Administration → Vitrine & promos**.
3. Rédigez le **texte d’accueil** (optionnel), la **remise annoncée globale** (%) et la **date de fin de promo** si besoin ; **ajoutez les produits** à afficher (liste dédiée, pas tout le stock).
4. Définissez dans `.env` :

```env
# URL publique du site (sans slash final) — utilisée pour les liens et QR codes
PUBLIC_BASE_URL=https://votre-domaine.com
```

5. Redéployez / redémarrez l’application pour prendre en compte les variables d’environnement.

## Base de données

Migrations Alembic : `e5f6a7b8c9d0` (`vitrine_and_bill_discount`), `f1a2b3c4d5e6` (`vitrine_product_selections`), `g8h9i0j1k2l3` (`vitrine_is_new_arrival`).

- **shops** : `vitrine_body`, `vitrine_discount_percent`, `vitrine_promo_end` (champs legacy éventuels : `vitrine_enabled`, `vitrine_slug`, `vitrine_title`).
- **vitrine_product_selections** : `shop_id`, `product_id`, `sort_order`, `is_promo`, `is_new_arrival` (liste des produits vitrine).
- **sales_bills** : `discount_rate`, `discount_amount`.
- **vitrine_visits** : `shop_id`, `visitor_key`, `created_at`.

## Dépendances

- **qrcode** (génération PNG pour le QR sur facture). Déclaré dans `requirements.txt`.

## Évolutions possibles (hors MVP)

- Plusieurs gabarits visuels, codes promo liés au ticket, intégration stricte remise vitrine ↔ caisse, export image pour WhatsApp, tableaux de bord analytics avancés.
