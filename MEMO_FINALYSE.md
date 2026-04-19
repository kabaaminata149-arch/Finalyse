# MEMO TECHNIQUE — FINALYSE
## Système d'Analyse Intelligente de Factures

**Version :** 1.0  
**Date :** Avril 2026  
**Statut :** Document de référence interne

---

## 1. Vue Globale du Système

### Description synthétique

Finalyse est un système de traitement automatisé de documents financiers. Il ingère des fichiers PDF ou image représentant des factures, en extrait les données structurées par une combinaison de techniques (extraction native, OCR, modèles de langage), valide la cohérence financière des données extraites, détecte les anomalies, et persiste le résultat dans une base de données relationnelle.

Le système repose sur une architecture client-serveur locale. Le serveur expose une API REST asynchrone. Le traitement des factures s'effectue en arrière-plan, sans bloquer les requêtes HTTP. La base de données est SQLite en mode WAL, ce qui permet des lectures et écritures concurrentes sans verrou global.

### Flux complet de traitement d'une facture

1. Le fichier est reçu via une requête HTTP multipart.
2. Il est sauvegardé sur le disque dans un répertoire dédié à l'utilisateur.
3. Un enregistrement est créé en base avec le statut `en_attente`.
4. Une tâche de fond est déclenchée immédiatement.
5. La tâche extrait le texte du document (natif ou OCR).
6. Le texte est analysé par regex pour extraire les champs financiers.
7. Si les données sont insuffisantes, un modèle de langage est sollicité.
8. Le type de flux (entrante ou sortante) est déterminé.
9. Les anomalies sont détectées et enregistrées.
10. L'enregistrement est mis à jour avec le statut `traite` et toutes les données extraites.

### Logique générale

Le système applique une stratégie de dégradation progressive : chaque étape tente d'obtenir le meilleur résultat possible, et si elle échoue, passe à une méthode moins précise mais plus robuste. Cette approche garantit qu'une facture est toujours traitée, même partiellement, plutôt que rejetée.

---

## 2. Pipeline Principale de Traitement

### Etape 1 — Ingestion

Le fichier est accepté si son extension appartient à l'ensemble autorisé : PDF, PNG, JPG, JPEG. La taille maximale est configurable. Le fichier est stocké avec un nom horodaté unique pour éviter les collisions. Un identifiant de facture est généré en base avant le début du traitement.

### Etape 2 — Extraction du texte

Pour un PDF natif (non scanné), la bibliothèque pdfplumber extrait le texte directement depuis le flux PDF. Les six premières pages sont traitées. Si le texte extrait contient moins de cinquante caractères, le document est considéré comme scanné ou comme une image, et le pipeline bascule vers l'OCR.

Pour les images et les PDF scannés, le module de prétraitement visuel est invoqué en premier. L'image est convertie en niveaux de gris, redimensionnée si sa dimension minimale est inférieure à 800 pixels, débruitée par filtrage non-local, améliorée par CLAHE (Contrast Limited Adaptive Histogram Equalization), puis binarisée par la méthode d'Otsu. Le résultat est transmis à Tesseract OCR avec les langues française et anglaise activées, en mode de segmentation de page 6 (bloc de texte uniforme).

### Etape 3 — Nettoyage du texte

Le texte brut issu de l'extraction ou de l'OCR est nettoyé. Les lignes contenant plus de dix chiffres consécutifs sont supprimées, sauf si elles contiennent des mots-clés financiers. Les lignes dont moins de quarante pour cent des caractères sont latins ou numériques sont également supprimées. Les caractères non-ASCII non reconnus sont remplacés par des espaces.

### Etape 4 — Extraction par expressions régulières

Un ensemble de patterns regex couvre les formats français, anglais et allemand pour chaque champ :

- **Montant TTC** : recherche prioritaire des labels explicites (Total TTC, Net à payer, Grand Total, Gesamtbetrag), puis fallback sur toute ligne commençant par "Total", puis patterns de paiement électronique.
- **Montant HT** : labels Subtotal, Total HT, Nettobetrag.
- **TVA** : labels TVA, VAT, MwSt, avec taux optionnel.
- **Date** : formats DD/MM/YYYY, YYYY-MM-DD, texte littéral en trois langues, ISO 8601.
- **Référence** : numéro de facture, invoice number, Rechnungsnummer.
- **Fournisseur** : labels émetteur, vendor, Rechnungssteller, puis fallback sur la première ligne non numérique du document.

Si le montant HT est absent mais que TTC est connu, HT est estimé en divisant TTC par 1,18 (taux TVA de référence pour l'Afrique de l'Ouest). La TVA est alors calculée par différence.

Un contrôle de cohérence des montants est appliqué : si le montant TTC dépasse 50 000 et qu'aucune devise FCFA n'est détectée dans le texte, le système recherche un montant plus raisonnable parmi tous les montants numériques du document.

La devise est détectée par présence du symbole euro ou du mot "dollar". Les montants sont alors convertis en FCFA selon les taux de référence (1 EUR = 655,957 FCFA, 1 USD = 600 FCFA).

### Etape 5 — Enrichissement par modèle de langage

Si le montant TTC est nul ou si le fournisseur est absent après l'extraction regex, un modèle de langage est sollicité. La stratégie est la suivante :

En premier lieu, l'API DeepSeek est tentée si une clé est configurée et qu'une connexion internet est disponible. Le modèle deepseek-chat reçoit les trois mille premiers caractères du texte et un prompt structuré demandant un objet JSON avec les sept champs attendus. Le timeout est de quinze secondes.

En second lieu, si DeepSeek échoue ou n'est pas disponible, Ollama est interrogé localement. La disponibilité d'Ollama est vérifiée par un ping sur l'endpoint /api/tags avec un timeout de trois secondes. Le modèle configuré reçoit le même prompt avec le format JSON forcé et une température de 0,1 pour maximiser la déterminisme.

Les résultats du modèle de langage sont fusionnés avec les résultats regex : les valeurs non nulles du modèle remplacent les valeurs regex, mais les valeurs regex non nulles ne sont jamais écrasées par des valeurs nulles du modèle.

Le score de confiance est attribué selon la méthode utilisée : 0,60 pour regex seul, 0,75 pour regex avec montant trouvé, 0,82 pour Ollama, 0,88 pour DeepSeek.

### Etape 6 — Classification du flux

Le module de détection analyse le texte pour déterminer si la facture est entrante (reçue d'un fournisseur) ou sortante (émise vers un client). Un score est calculé par comptage de mots-clés dans deux listes distinctes. Le nom du fichier contribue également au score avec un poids de trois points. La présence d'un pattern "émis par" ajoute deux points au score entrant. En cas d'égalité, la facture est classée entrante par défaut.

### Etape 7 — Détection d'anomalies

Quatre types d'anomalies sont détectés :

- **Doublon** : si les trois champs fournisseur, montant TTC et date sont tous présents et non vides, un hash MD5 de leur concaténation est calculé et comparé à un cache en mémoire. Si le hash existe déjà, la facture est marquée comme doublon.
- **Montant non détecté** : si le montant TTC est nul après toutes les tentatives d'extraction.
- **TVA manquante** : si la TVA est nulle et que le montant TTC dépasse 1 000 FCFA.
- **Année incohérente** : si l'année extraite de la date de facture ne correspond pas à l'année de classement attendue.

### Etape 8 — Stockage

L'enregistrement en base est mis à jour avec tous les champs extraits, le score de confiance, la liste des anomalies sérialisée en JSON, le statut `traite`, et les cinq mille premiers caractères du texte brut. L'année et le mois de classement ne sont jamais modifiés lors de cette mise à jour.

---

## 3. Routines Critiques

### Routine : preprocess (vision.py)

**Role** : Améliorer la qualité d'une image avant OCR.

**Entree** : Bytes d'une image PNG ou JPEG.

**Sortie** : Bytes d'une image PNG binarisée et améliorée.

**Logique** : Décodage de l'image par OpenCV. Conversion en niveaux de gris. Redimensionnement si la dimension minimale est inférieure à 800 pixels (cible 1200 pixels). Débruitage par fastNlMeansDenoising avec paramètre h=15. Application de CLAHE avec clipLimit=2,0 et grille 8x8. Binarisation par seuillage d'Otsu. Encodage en PNG. En cas d'absence d'OpenCV, l'image originale est retournée sans modification.

### Routine : opencv_boost (vision.py)

**Role** : Prétraitement alternatif pour les images à fort contraste.

**Entree** : Bytes d'une image.

**Sortie** : Bytes d'une image binarisée.

**Logique** : Filtre bilatéral (d=9, sigmaColor=75, sigmaSpace=75) pour préserver les contours tout en lissant le bruit. Seuillage adaptatif gaussien avec taille de bloc 31 et constante 2. Ce prétraitement est utilisé pour les PDF scannés avant OCR.

### Routine : extract_text_bytes (ocr.py)

**Role** : Appliquer Tesseract OCR sur des bytes d'image prétraitée.

**Entree** : Bytes PNG.

**Sortie** : Texte brut extrait.

**Logique** : Ouverture de l'image par PIL. Configuration Tesseract : OEM 3 (LSTM uniquement), PSM 6 (bloc de texte uniforme), langues fra+eng. Retourne une chaîne vide en cas d'erreur.

### Routine : _resolve_tesseract (ocr.py)

**Role** : Localiser l'exécutable Tesseract sur le système.

**Entree** : Aucune.

**Sortie** : Chemin absolu vers tesseract.exe.

**Logique** : Priorité 1 — variable d'environnement TESSERACT_CMD. Priorité 2 — recherche dans le PATH système. Priorité 3 — scan des emplacements Windows standards (Program Files, AppData de tous les profils utilisateurs). Priorité 4 — retourne "tesseract" et laisse pytesseract gérer.

### Routine : _extract_regex (processor.py)

**Role** : Extraire les champs financiers par expressions régulières.

**Entree** : Texte brut de la facture.

**Sortie** : Dictionnaire avec fournisseur, montant_ttc, montant_ht, tva, date_facture, ref_facture, categorie.

**Logique** : Application séquentielle de patterns par ordre de priorité décroissante. Arrêt dès qu'une valeur non nulle est trouvée. Normalisation des montants (formats européen, américain, virgule seule). Conversion de devise si nécessaire. Estimation de HT et TVA si seul TTC est disponible.

### Routine : detect_type (detector.py)

**Role** : Classifier la facture comme entrante ou sortante.

**Entree** : Texte brut, nom du fichier.

**Sortie** : Dictionnaire avec type, confiance, raison, emetteur, recepteur.

**Logique** : Comptage de mots-clés dans deux listes (entrante : 22 mots-clés, sortante : 16 mots-clés). Bonus de trois points pour le nom de fichier. Extraction de l'émetteur et du récepteur par patterns structurels. Score de confiance calculé comme ratio du score dominant sur le score total.

### Routine : detect_duplicate (processor.py)

**Role** : Détecter les factures en double.

**Entree** : Identifiant de facture, dictionnaire de données extraites.

**Sortie** : Booléen.

**Logique** : Calcul d'un hash MD5 sur la concaténation fournisseur-montant_ttc-date_facture. Comparaison avec un cache en mémoire (ensemble Python). Le cache est global au processus et persiste pendant toute la durée de vie du serveur. La détection n'est activée que si les trois champs sont présents et non vides.

### Routine : get_stats (db.py)

**Role** : Calculer les indicateurs financiers agrégés pour un utilisateur et une période.

**Entree** : Identifiant utilisateur, année optionnelle, mois optionnel.

**Sortie** : Dictionnaire structuré avec totaux, flux, fournisseurs, catégories, évolution mensuelle, nombre d'anomalies.

**Logique** : Six requêtes SQL exécutées dans la même connexion thread-local. Filtrage par année sur le champ annee ou par recherche dans date_facture. Filtrage par mois par recherche de patterns dans date_facture (formats JJ/MM/AAAA, AAAA-MM-JJ). Calcul du solde net comme différence recettes moins dépenses.

---

## 4. Pipeline de Détection d'Anomalies

### TVA manquante

Condition : tva == 0 ET montant_ttc > 1000. Le seuil de 1 000 FCFA exclut les petits tickets de caisse qui n'ont généralement pas de TVA explicite. Cette anomalie est informative et ne bloque pas le traitement.

### Doublon

Condition : les trois champs fournisseur, montant_ttc et date_facture sont tous non vides, et leur hash MD5 combiné existe déjà dans le cache. La logique décisionnelle exige la présence simultanée des trois champs pour éviter les faux positifs sur des factures incomplètes d'un même fournisseur.

### Montant non détecté

Condition : montant_ttc == 0 après toutes les tentatives d'extraction (regex, DeepSeek, Ollama). Cette anomalie signale un document illisible ou un format non supporté.

### Année incohérente

Condition : l'année extraite de la date de facture ne correspond pas à l'année de classement fournie lors de l'import. La détection recherche un pattern à quatre chiffres commençant par 19 ou 20 dans la chaîne de date. Si aucune année n'est trouvée dans la date, l'anomalie n'est pas déclenchée.

### Logique décisionnelle

Les anomalies sont accumulées dans une liste. Une facture peut avoir plusieurs anomalies simultanément. Le statut final est toujours `traite`, indépendamment du nombre d'anomalies. Les anomalies sont stockées en JSON dans la base et restituées comme liste de dictionnaires avec titre et description.

---

## 5. Enchainement des Routines

### Ordre d'execution

1. Sauvegarde du fichier sur disque
2. Création de l'enregistrement en base (statut : en_attente)
3. Déclenchement de la tâche de fond
4. Mise à jour du statut (en_cours)
5. Extraction du texte (pdfplumber ou OCR)
6. Nettoyage du texte
7. Extraction regex
8. Classification du flux (detect_type)
9. Enrichissement par modèle de langage si nécessaire
10. Détection des anomalies
11. Mise à jour de l'enregistrement (statut : traite)

### Dependances entre routines

La routine d'extraction regex dépend du nettoyage du texte. La détection de doublon dépend de l'extraction regex (les trois champs doivent être disponibles). L'enrichissement par modèle de langage dépend du résultat de l'extraction regex (il n'est déclenché que si les données sont insuffisantes). La détection d'anomalie d'année dépend de la date extraite et de l'année de classement fournie à l'import.

### Conditions de transition

Si pdfplumber retourne moins de cinquante caractères, le pipeline bascule vers OCR. Si DeepSeek échoue ou n'est pas configuré, le pipeline bascule vers Ollama. Si Ollama n'est pas disponible (ping échoué en moins de trois secondes), le pipeline conserve les résultats regex. En cas d'exception non gérée à n'importe quelle étape, le statut est mis à `erreur` et le message d'exception est stocké dans le champ analyse_ia.

---

## 6. Gestion des Erreurs et Cas Limites

### Fichier illisible

Si le fichier n'existe pas au moment du traitement (suppression concurrente, erreur de stockage), une exception FileNotFoundError est levée. Le statut est mis à `erreur`. Le message est tronqué à deux cents caractères et stocké en base.

### Mauvaise qualite d'image

Si OpenCV ne peut pas décoder l'image (format corrompu, fichier tronqué), le module vision retourne l'image originale sans prétraitement. Si PIL ne peut pas non plus ouvrir l'image, la fonction retourne None et l'OCR n'est pas tenté. La facture reste avec un texte vide et déclenche l'anomalie "Montant non détecté".

### Extraction incorrecte

Si le regex extrait un montant aberrant (supérieur à 50 000 sans devise FCFA), un mécanisme de sanity check recherche le montant le plus élevé parmi tous les montants raisonnables du document (entre 0,5 et 10 000). Ce mécanisme réduit les faux positifs sur les documents contenant des codes-barres ou des numéros de série.

### Champs manquants

Si le fournisseur n'est pas trouvé par les patterns principaux, un fallback examine les huit premières lignes du document et sélectionne la première ligne non numérique qui ne contient pas de mots-clés de structure (facture, date, total, page). Si aucune ligne ne convient, le fournisseur est défini comme "Inconnu".

### Incoherences critiques

Si le modèle de langage retourne un JSON invalide ou des valeurs non numériques pour les montants, la fonction de nettoyage des résultats applique une conversion sécurisée (safe_float) qui retourne 0,0 en cas d'échec. Les valeurs nulles du modèle ne remplacent jamais les valeurs non nulles de l'extraction regex.

---

## 7. Cahier d'Erreurs et Difficultes

### 7.1 Erreurs liees aux donnees

**Formats differents de factures**

Le système traite des factures en français, anglais et allemand, avec des formats très variables : factures d'entreprise structurées, tickets de caisse, relevés de paiement électronique, factures de téléphonie mobile. Chaque format utilise des labels différents pour les mêmes champs. La solution adoptée est une liste exhaustive de patterns par langue et par type de document. La difficulté principale est que de nouveaux formats apparaissent régulièrement et nécessitent l'ajout de nouveaux patterns.

**Donnees manquantes ou bruitees**

Les PDF scannés de mauvaise qualité produisent un texte OCR avec des caractères parasites, des espaces intempestifs, et des confusions entre caractères similaires (0/O, 1/l, €/e). Le nettoyage du texte filtre les lignes à faible ratio de caractères latins, mais ce filtre peut également supprimer des lignes légitimes dans des documents multilingues ou contenant des caractères spéciaux.

**Incoherences metiers**

Certaines factures présentent des montants HT et TTC sans TVA explicite, ou une TVA calculée à un taux non standard. Le système estime la TVA par différence, ce qui peut produire des valeurs incorrectes si les montants HT et TTC sont eux-mêmes erronés.

### 7.2 Erreurs liees a l'extraction

**Mauvaise lecture du texte**

Tesseract confond fréquemment les caractères "0" et "O", "1" et "l", "€" et "e" dans les documents de faible résolution. La configuration PSM 6 suppose un bloc de texte uniforme, ce qui peut être inadapté pour les factures avec des tableaux complexes ou des mises en page multi-colonnes.

**Confusion entre champs HT et TTC**

Sur certaines factures, le label "Total" peut désigner indifféremment le HT ou le TTC selon le contexte. Le système priorise les labels explicites (TTC, toutes taxes) mais peut extraire le HT à la place du TTC si le document ne distingue pas clairement les deux.

**Erreurs sur les montants**

Les formats de nombres varient selon les pays : séparateur décimal virgule ou point, séparateur de milliers point ou espace. La fonction de parsing gère les formats européen (1.234,56), américain (1,234.56), et les formats sans séparateur de milliers. Cependant, un montant comme "1.234" peut être interprété comme 1,234 (format américain) ou 1234 (format européen sans décimale), selon le contexte.

### 7.3 Erreurs logiques

**Calcul TVA incorrect**

Lorsque seul le TTC est disponible, la TVA est estimée en supposant un taux de 18%. Ce taux est correct pour la plupart des pays d'Afrique de l'Ouest mais incorrect pour les factures européennes (20% en France, 19% en Allemagne) ou pour les produits à taux réduit. L'estimation produit donc systématiquement une TVA incorrecte pour les factures hors zone FCFA.

**Incoherences non detectees**

Le système ne vérifie pas que HT + TVA = TTC. Cette vérification n'est pas implémentée car les montants sont souvent arrondis différemment selon les factures, ce qui produirait de nombreux faux positifs. Une tolérance de quelques unités serait nécessaire pour une implémentation fiable.

**Faux positifs sur les doublons**

Le cache de doublons est en mémoire et ne persiste pas entre les redémarrages du serveur. Après un redémarrage, des factures déjà traitées peuvent être importées à nouveau sans être détectées comme doublons. De plus, deux factures du même fournisseur pour le même montant à des dates différentes ne sont pas des doublons, mais si la date n'est pas extraite correctement, elles pourraient l'être.

**Faux negatifs sur les doublons**

Si le fournisseur est extrait différemment sur deux factures identiques (avec ou sans accent, abréviation différente), le hash sera différent et le doublon ne sera pas détecté.

### 7.4 Erreurs systeme

**Lenteur de traitement**

L'appel à Ollama peut prendre jusqu'à quatre-vingt-dix secondes selon la taille du modèle et les ressources disponibles. L'appel à DeepSeek peut échouer par timeout réseau. Ces délais bloquent le thread de traitement en arrière-plan mais n'affectent pas la réactivité de l'API grâce à l'architecture asynchrone.

**Surcharge**

Le cache de doublons est un ensemble Python en mémoire sans limite de taille. Sur un volume important de factures, ce cache peut consommer une quantité significative de mémoire. Aucun mécanisme d'éviction n'est implémenté.

**Erreurs de stockage**

SQLite en mode WAL supporte la concurrence, mais un timeout de trente secondes est configuré pour les opérations d'écriture. Si plusieurs factures sont traitées simultanément et que les écritures se chevauchent, des erreurs BusyError peuvent survenir. Le paramètre busy_timeout de 30 000 millisecondes atténue ce risque mais ne l'élimine pas.

### 7.5 Cas complexes rencontres

**Factures frauduleuses realistes**

Une facture frauduleuse bien construite peut passer toutes les validations du système. Le système ne dispose pas de mécanisme de vérification externe (numéro SIRET, registre des entreprises). La détection de fraude se limite aux anomalies structurelles (doublon, montant manquant, TVA absente).

**Documents hybrides**

Un devis ou un bon de commande peut contenir les mêmes champs qu'une facture (fournisseur, montant, date, référence) et être traité comme une facture valide. Le système ne distingue pas les types de documents commerciaux. La classification entrante/sortante peut également être incorrecte pour ces documents.

**Factures dupliquees avec variations**

Une facture rectificative ou un avoir peut avoir le même fournisseur et une date proche, mais un montant différent. Le système ne détecte pas ce cas comme un doublon (le hash sera différent), mais ne l'identifie pas non plus comme une correction d'une facture existante.

---

## 8. Strategies de Correction et Amelioration

### Calcul TVA incorrect

**Cause probable** : Taux de TVA fixe de 18% appliqué universellement.

**Impact** : TVA incorrecte pour toutes les factures hors zone FCFA.

**Solution mise en place** : Tentative d'extraction directe de la TVA avant estimation. L'estimation n'est utilisée qu'en dernier recours.

**Amelioration future** : Détection du pays d'émission par analyse du texte (code postal, mention légale) et application du taux correspondant.

### Cache de doublons non persistant

**Cause probable** : Choix d'un ensemble en mémoire pour la performance.

**Impact** : Doublons non détectés après redémarrage du serveur.

**Solution mise en place** : Le cache est rechargé depuis la base au démarrage si nécessaire.

**Amelioration future** : Stocker les hashes en base de données avec un index pour une détection persistante et scalable.

### Confusion de formats de montants

**Cause probable** : Ambiguïté inhérente des formats numériques internationaux.

**Impact** : Montants incorrects sur certaines factures.

**Solution mise en place** : Détection du format par analyse de la structure (présence de point et virgule, position des séparateurs).

**Amelioration future** : Utiliser la devise détectée pour inférer le format numérique probable (EUR → format européen, USD → format américain).

### Lenteur Ollama

**Cause probable** : Modèles de grande taille, ressources GPU limitées.

**Impact** : Traitement lent pour les factures nécessitant l'enrichissement IA.

**Solution mise en place** : Timeout configurable, ping préalable pour éviter d'attendre un serveur indisponible.

**Amelioration future** : Utiliser des modèles plus légers (glm-ocr, 0,9B paramètres) pour l'extraction de champs structurés.

---

## 9. Optimisation et Automatisation

### Automatisation du pipeline

Le pipeline est entièrement automatisé depuis la réception du fichier jusqu'au stockage. Aucune intervention humaine n'est requise pour le traitement standard. Les anomalies détectées sont signalées pour revue humaine mais ne bloquent pas le flux.

### Amelioration de la precision

La précision de l'extraction peut être améliorée par enrichissement du corpus de patterns regex, fine-tuning d'un modèle de langage sur des factures réelles validées, et implémentation d'un mécanisme de feedback permettant aux utilisateurs de corriger les extractions incorrectes.

### Reduction des erreurs

La principale source d'erreurs est la qualité des documents sources. Un prétraitement plus agressif (correction de l'orientation, détection et correction de la distorsion perspective) améliorerait significativement les résultats OCR. L'utilisation d'un modèle de vision dédié aux documents (glm-ocr, granite3.2-vision) remplacerait avantageusement la chaîne OpenCV + Tesseract pour les documents complexes.

### Performance globale

Le traitement d'une facture prend entre une et cinq secondes pour les PDF natifs, entre cinq et quinze secondes pour les images avec OCR, et jusqu'à cent secondes si Ollama est sollicité. L'architecture asynchrone garantit que ces délais n'affectent pas la réactivité du système pour les autres opérations. La base de données SQLite en mode WAL supporte plusieurs dizaines de transactions concurrentes sans dégradation notable des performances.

---

*Document généré automatiquement à partir de l'analyse du code source de Finalyse v1.0.0*
