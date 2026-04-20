# Requirements Document

## Introduction

Cette fonctionnalité améliore la page Rapports de l'application Finalyse (PyQt6 + FastAPI + SQLite) en permettant le filtrage des rapports par un ou plusieurs dossiers sélectionnés. Actuellement, la sélection de dossier est limitée à un seul dossier via un `QComboBox`. La nouvelle fonctionnalité doit permettre la multi-sélection de dossiers, propager ce filtre à tous les exports (PDF, CSV, email) et afficher le nom des dossiers sélectionnés dans les rapports générés.

## Glossaire

- **RapportsPage** : Page PyQt6 affichant le rapport financier (`frontend/pages/rapports.py`)
- **DossierSelector** : Widget de sélection de dossier(s) remplaçant le `QComboBox` actuel
- **ExportWorker** : Thread PyQt6 gérant les exports asynchrones (`_ExportWorker`)
- **StatsWorker** : Thread PyQt6 chargeant les statistiques (`_StatsWorker`)
- **API_Client** : Client HTTP PyQt6 communiquant avec le backend FastAPI (`frontend/api_client.py`)
- **ExportRoute** : Routes FastAPI gérant les exports (`backend/routes/export.py`)
- **DashboardRoute** : Route FastAPI retournant les statistiques (`backend/routes/dashboard.py`)
- **DB** : Couche base de données SQLite (`backend/database/db.py`)
- **dossier_ids** : Liste d'identifiants entiers représentant les dossiers sélectionnés
- **Rapport PDF** : Document PDF généré par `export_pdf` dans `backend/services/export_service.py`
- **Rapport CSV** : Fichier CSV généré par `export_csv` dans `backend/services/export_service.py`

---

## Requirements

### Requirement 1 : Sélection multi-dossiers dans l'interface

**User Story :** En tant qu'utilisateur, je veux sélectionner un ou plusieurs dossiers sur la page Rapports, afin de filtrer les données financières affichées selon mes besoins.

#### Acceptance Criteria

1. THE DossierSelector SHALL remplacer le `QComboBox` actuel par un widget permettant la sélection de zéro, un ou plusieurs dossiers parmi la liste des dossiers disponibles.
2. THE DossierSelector SHALL proposer une option "Tous les dossiers" qui, lorsqu'elle est activée, désélectionne tous les dossiers individuels.
3. WHEN l'utilisateur sélectionne "Tous les dossiers", THE DossierSelector SHALL désactiver la sélection individuelle de dossiers et transmettre une liste vide (`dossier_ids=[]`) au filtre.
4. WHEN l'utilisateur sélectionne un ou plusieurs dossiers individuels, THE DossierSelector SHALL désactiver l'option "Tous les dossiers" et transmettre la liste des identifiants sélectionnés.
5. WHEN aucun dossier n'est sélectionné et "Tous les dossiers" n'est pas actif, THE RapportsPage SHALL bloquer tout chargement de données et afficher un message d'erreur indiquant qu'au moins un dossier doit être sélectionné.
6. THE DossierSelector SHALL afficher le nombre de dossiers sélectionnés dans son libellé résumé (ex : "3 dossiers sélectionnés").

---

### Requirement 2 : Propagation du filtre aux statistiques du tableau de bord

**User Story :** En tant qu'utilisateur, je veux que les statistiques affichées sur la page Rapports reflètent uniquement les dossiers sélectionnés, afin d'obtenir une analyse financière précise.

#### Acceptance Criteria

1. WHEN l'utilisateur modifie la sélection de dossiers, THE StatsWorker SHALL recharger les statistiques en transmettant la liste `dossier_ids` au endpoint `/api/dashboard`.
2. THE API_Client SHALL transmettre le paramètre `dossier_ids` sous forme de liste d'entiers à la route `/api/dashboard` via des query parameters répétés (ex : `dossier_id=1&dossier_id=2`).
3. THE DashboardRoute SHALL accepter un paramètre `dossier_ids` de type `List[int]` et filtrer les factures en conséquence.
4. WHEN `dossier_ids` est vide ou absent, THE DB SHALL retourner les statistiques de tous les dossiers de l'utilisateur.
5. WHEN `dossier_ids` contient un ou plusieurs identifiants, THE DB SHALL retourner uniquement les statistiques des factures appartenant à ces dossiers.

---

### Requirement 3 : Filtrage du rapport PDF par dossier(s)

**User Story :** En tant qu'utilisateur, je veux que le rapport PDF exporté soit filtré selon les dossiers sélectionnés et mentionne leur nom, afin d'avoir un document précis et traçable.

#### Acceptance Criteria

1. WHEN l'utilisateur déclenche l'export PDF, THE ExportWorker SHALL transmettre la liste `dossier_ids` à la route `/api/export/pdf`.
2. THE ExportRoute SHALL accepter un paramètre `dossier_ids` de type `List[int]` et filtrer les factures récupérées depuis la DB en conséquence.
3. WHEN `dossier_ids` contient un ou plusieurs identifiants, THE Rapport PDF SHALL afficher le ou les noms des dossiers sélectionnés dans son en-tête ou sa section de contexte.
4. WHEN `dossier_ids` est vide, THE Rapport PDF SHALL indiquer "Tous les dossiers" dans son en-tête.
5. IF l'utilisateur tente d'exporter un PDF sans aucun dossier sélectionné et sans "Tous les dossiers" actif, THEN THE RapportsPage SHALL afficher un message d'erreur et ne pas déclencher l'export.

---

### Requirement 4 : Filtrage de l'export CSV par dossier(s)

**User Story :** En tant qu'utilisateur, je veux que l'export CSV soit filtré selon les dossiers sélectionnés, afin d'obtenir uniquement les données pertinentes.

#### Acceptance Criteria

1. WHEN l'utilisateur déclenche l'export CSV, THE ExportWorker SHALL transmettre la liste `dossier_ids` à la route `/api/export/csv`.
2. THE ExportRoute SHALL accepter un paramètre `dossier_ids` de type `List[int]` pour l'endpoint `/api/export/csv` et filtrer les factures en conséquence.
3. WHEN `dossier_ids` est vide, THE ExportRoute SHALL exporter toutes les factures de l'utilisateur sans filtre de dossier.
4. IF l'utilisateur tente d'exporter un CSV sans aucun dossier sélectionné et sans "Tous les dossiers" actif, THEN THE RapportsPage SHALL afficher un message d'erreur et ne pas déclencher l'export.

---

### Requirement 5 : Filtrage de l'envoi email par dossier(s)

**User Story :** En tant qu'utilisateur, je veux que le rapport envoyé par email soit filtré selon les dossiers sélectionnés, afin que le destinataire reçoive uniquement les données pertinentes.

#### Acceptance Criteria

1. WHEN l'utilisateur déclenche l'envoi email, THE ExportWorker SHALL transmettre la liste `dossier_ids` à la route `/api/export/send-report`.
2. THE ExportRoute SHALL accepter un paramètre `dossier_ids` de type `List[int]` dans le body de la requête `SendReportIn` et filtrer les factures en conséquence.
3. WHEN `dossier_ids` contient un ou plusieurs identifiants, THE Rapport PDF joint à l'email SHALL afficher le ou les noms des dossiers sélectionnés.
4. IF l'utilisateur tente d'envoyer un email sans aucun dossier sélectionné et sans "Tous les dossiers" actif, THEN THE RapportsPage SHALL afficher un message d'erreur et ne pas déclencher l'envoi.

---

### Requirement 6 : Résolution des noms de dossiers pour les rapports

**User Story :** En tant que système, je veux pouvoir résoudre les noms des dossiers à partir de leurs identifiants, afin de les afficher dans les rapports PDF et les emails.

#### Acceptance Criteria

1. THE DB SHALL exposer une fonction `get_dossiers_by_ids(uid, dossier_ids)` retournant la liste des dossiers correspondant aux identifiants fournis pour un utilisateur donné.
2. WHEN `dossier_ids` est vide, THE DB SHALL retourner tous les dossiers de l'utilisateur.
3. THE ExportRoute SHALL utiliser `get_dossiers_by_ids` pour résoudre les noms des dossiers avant de générer le PDF ou l'email.
4. THE `export_pdf` SHALL accepter un paramètre `dossier_label` de type `str` et l'inclure dans l'en-tête du rapport généré.
