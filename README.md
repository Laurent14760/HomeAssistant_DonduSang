# EFS – Collectes de don du sang pour Home Assistant

Intégration personnalisée qui interroge l’API Carto v3 publique de l’Établissement français du sang (EFS) et expose les prochaines collectes autour d’une commune ou du domicile : date, lieu, horaires, places totales et restantes, taux de remplissage et lien de prise de rendez-vous. Les données alimentent des capteurs, un calendrier et un capteur binaire, utilisables tels quels dans les tableaux de bord et les automatisations.

| Élément | Valeur |
|---|---|
| Domaine | `efs_dondesang` |
| Version | 1.4.1 |
| Home Assistant minimum | 2024.11 (2026.11 recommandé : installation par le Marketplace) |
| Classe IoT | `cloud_polling` (1 appel par instance et par intervalle) |
| Dépendances Python | aucune (aiohttp fourni par Home Assistant) |
| Configuration | 100 % interface, aucune ligne de YAML |
| Installation | Marketplace de Home Assistant (2026.11+), dépôt ajouté par lien |

---

## 1. Contenu du package

```
efs_dondesang/
├── hacs.json
├── README.md                         ← ce document
├── custom_components/efs_dondesang/
│   ├── __init__.py                   mise en place, rechargement, cache disque
│   ├── api.py                        clients asynchrones API Carto EFS + API Géo
│   ├── parser.py                     logique métier pure (géométrie, filtres, places)
│   ├── coordinator.py                DataUpdateCoordinator + repli sur cache
│   ├── config_flow.py                assistant d'installation et options
│   ├── sensor.py / calendar.py / binary_sensor.py
│   ├── services.py, services.yaml   action « Rechercher des collectes » (réponse à la demande)
│   ├── search.py                    logique pure de l'action (commune, cache, réponse)
│   ├── diagnostics.py
│   ├── brand/                       icône et logo (goutte de sang)
│   ├── location.py                  choix et suivi du lieu de recherche
│   ├── manifest.json, strings.json
│   └── translations/fr.json, en.json
├── examples/
│   ├── tableau_de_bord.yaml          cartes Markdown, Jauge, Carte, Agenda
│   └── automatisations.yaml          veille de collecte, places, ouverture du planning
└── tests/                            pytest sur réponses JSON enregistrées
```

---

## 2. Installation pas à pas

Exemple suivi tout au long de ce chapitre : collectes de **sang total** autour de **Bretteville-sur-Odon (14760)**, dans un rayon de **10 km**, sur les **30 prochains jours**.

### 2.1 Prérequis

- **Home Assistant 2026.11 ou plus récent** : l’installation passe par le **Marketplace**, intégré à Home Assistant depuis cette version (il remplace HACS, dont il reprend les dépôts déjà installés). Sur une version plus ancienne, voir § 2.9.
- Un **compte GitHub** relié au Marketplace : il est exigé pour ajouter un dépôt qui n’est pas dans le catalogue, ce qui est le cas de cette intégration et de sa carte.
- Un accès Internet sortant vers `oudonner.api.efs.sante.fr` (API de l’EFS) et `geo.api.gouv.fr` (communes d’un code postal).

### 2.2 Relier GitHub au Marketplace (une seule fois)

1. **Paramètres → Marketplace**.
2. Au premier accès, lire et accepter l’avertissement sur les extensions communautaires.
3. Lancer la connexion GitHub proposée : le Marketplace affiche un code ; l’ouvrir sur github.com/login/device, saisir le code et autoriser. Aucun mot de passe n’est saisi dans Home Assistant.

### 2.3 Installer l’intégration

1. **Paramètres → Marketplace → ⋮ → Add from link** (« Ajouter depuis un lien »).
2. URL : `https://github.com/Laurent14760/HomeAssistant_DonduSang` ; si une catégorie est demandée : **Intégration**.
3. Ouvrir la fiche « EFS – Collectes de don du sang », puis **Install** (dernière version, 1.4.1 ou plus).
4. **Redémarrer Home Assistant** : Paramètres → Système → ⏻ (en haut à droite) → **Redémarrer Home Assistant**. Le redémarrage est indispensable pour charger une intégration.

### 2.4 Créer l’instance « Bretteville-sur-Odon »

1. **Paramètres → Appareils et services → + Ajouter une intégration**, rechercher **EFS**.
2. Choisir **Une commune, par son code postal**, saisir `14760`, **Valider**. (Si un code postal couvre plusieurs communes, un second écran demande laquelle ; 14760 n’en couvre qu’une.)
3. Écran des réglages, valeurs de l’exemple :

| Réglage | Valeur de l’exemple | Pourquoi |
|---|---|---|
| Rayon de recherche | **10** km | Bretteville et sa couronne (Verson, Carpiquet, Ifs, Caen…) |
| Type de don | **Sang total** | Compteurs de places et lien de rendez-vous du sang total |
| Inclure les collectes professionnelles | Non | Elles sont réservées au personnel ou aux élèves |
| Horizon | **30** jours | Délai couvert à partir d’aujourd’hui |
| Nombre max. de collectes listées | 10 | Suffisant pour l’agenda (jusqu’à 30) |
| Intervalle de rafraîchissement | 60 min | Bon compromis pour suivre les places |
| Seuil « collecte proche » | 7 jours | Capteur binaire utilisé par les automatisations |
| Exposer les Maisons du don | Non | Oui pour lister la Maison du don de Caen |

4. **Valider**. L’instance « EFS Bretteville-sur-Odon » apparaît avec un appareil et ses entités :

| Entité | Contenu |
|---|---|
| `sensor.efs_bretteville_sur_odon_prochaine_collecte` | Début de la prochaine collecte ; attributs lieu, adresse, horaires, places, lien de RDV |
| `sensor.efs_bretteville_sur_odon_prochaine_collecte_places_restantes` / `…_places_totales` / `…_taux_remplissage` | Compteurs de la prochaine collecte (`unknown` tant que le planning n’est pas ouvert) |
| `sensor.efs_bretteville_sur_odon_collectes_a_venir` | Nombre de collectes sur 30 jours ; attribut `collectes` (liste) |
| `calendar.efs_bretteville_sur_odon_collectes` | Un événement par créneau |
| `binary_sensor.efs_bretteville_sur_odon_collecte_proche` | Actif si une collecte a lieu dans les 7 jours |

Les identifiants dérivent du nom de l’instance ; vérifier les vôtres dans Paramètres → Appareils et services → EFS → (instance) → entités. Une instance créée avant la 1.3.0 porte des identifiants sans le nom de la zone (`sensor.efs_prochaine_collecte`).

### 2.5 Installer la carte d’affichage

1. **Paramètres → Marketplace → ⋮ → Add from link**.
2. URL : `https://github.com/Laurent14760/HomeAssistant_DonduSang_Card` ; si une catégorie est demandée : **Tableau de bord** (*Dashboard*).
3. Ouvrir la fiche « EFS – Carte des collectes de don du sang », puis **Install** (1.3.1 ou plus). Le Marketplace déclare lui-même la ressource du tableau de bord ; aucun redémarrage n’est nécessaire.
4. Recharger le navigateur sans cache (Ctrl + Maj + R). Application mobile : Paramètres → Application compagnon → Dépannage → **Réinitialiser le cache du frontend**, puis fermer complètement l’application et la rouvrir.

### 2.6 Vérifier

1. **Outils de développement → États** : `sensor.efs_bretteville_sur_odon_prochaine_collecte` affiche une date ; ses attributs donnent le lieu et les places.
2. **Outils de développement → Actions** : choisir « Rechercher des collectes » (`efs_dondesang.rechercher_collectes`), passer en mode YAML et lancer :

```yaml
action: efs_dondesang.rechercher_collectes
data:
  code_postal: "14760"
  rayon_km: 10
  type_don: sang
  jours: 30
```

La réponse liste les collectes (`collectes`), leur nombre (`nombre`) et `api_disponible: true`.
3. **Paramètres → Système → Journaux** : aucune erreur `efs_dondesang`.

### 2.7 Ajouter les cartes au tableau de bord

Tableau de bord → ✏️ **Modifier** → **+ Ajouter une carte** → rechercher « EFS – Collectes de don du sang » (réglages dans l’éditeur visuel), ou **Manuel** pour coller l’une des propositions du chapitre 5.

### 2.8 Mettre à jour

Les nouvelles versions apparaissent dans **Paramètres → Mises à jour**, à côté de celles de Home Assistant. Pour une release publiée à l’instant : fiche du dépôt dans le Marketplace → ⋮ → **Refresh information**. Après la mise à jour de l’intégration, **redémarrer Home Assistant** ; après celle de la carte, vider le cache du navigateur.

### 2.9 Autres modes d’installation

- **Home Assistant antérieur à 2026.11 (HACS)** : HACS → ⋮ → **Dépôts personnalisés**, mêmes URL et catégories, puis **Télécharger**. À la mise à niveau vers 2026.11, le Marketplace reprend ces dépôts et leurs mises à jour sans réinstallation.
- **Manuelle** : copier `custom_components/efs_dondesang` dans `/config/custom_components/` (modules *Samba share* ou *Studio Code Server*), redémarrer. Pour la carte : copier `dist/efs-collectes-card.js` dans `/config/www/`, puis Paramètres → Tableaux de bord → ⋮ → Ressources → `/local/efs-collectes-card.js?v=1.3.1`, type *Module JavaScript*. Pas de notification de mise à jour dans ce mode.

---

## 3. Configuration

**Paramètres → Appareils et services → Ajouter une intégration → « EFS »**

L’assistant propose trois points de référence :

- **Position de la maison** : celle définie dans Paramètres → Système → Général. Elle est suivie : si vous la modifiez, la recherche suit.
- **Une commune, par son code postal** : la commune est résolue par l’API Géo de l’État (`geo.api.gouv.fr`). Si le code postal couvre plusieurs communes (cas fréquent en zone rurale), un écran permet de choisir la bonne ; son centre géographique devient le point de recherche.
- **Une zone, une personne ou un traceur** : la recherche se fait autour de la position de l’entité choisie. Une zone (`zone.travail`) donne un point fixe que l’on déplace depuis Paramètres → Zones ; une personne ou un traceur donne un point mobile (voir ci-dessous).

Viennent ensuite les réglages :

| Réglage | Défaut | Commentaire |
|---|---|---|
| Rayon de recherche | 10 km | 1 à 50 km. Le rectangle interrogé est converti depuis le rayon puis filtré au cercle exact. |
| Type de don | Sang total | Sang total, plasma ou plaquettes : détermine les compteurs de places (ST, PLA, CPA) et le lien de RDV utilisés. |
| Inclure les collectes professionnelles | Non | Entreprises, lycées, administrations… généralement réservées au personnel ou aux élèves. |
| Horizon | 60 jours | Les collectes au-delà ne sont pas remontées. |
| Nombre max. de collectes listées | 10 | Plafonné à 30 pour rester sous la limite de 16 Ko d’attributs du recorder. |
| Intervalle de rafraîchissement | 60 min | 15 min à 24 h. Les places évoluent vite, les dates rarement. |
| Seuil « collecte proche » | 7 jours | Pilote le capteur binaire. |
| Exposer les Maisons du don | Non | Ajoute les sites fixes à proximité dans un attribut. |

### Modifier après l’installation : bouton « Configurer »

**Paramètres → Appareils et services → EFS – Collectes de don du sang → (instance) → Configurer** ouvre un menu :

- **Changer de localisation** : mêmes trois choix qu’à l’installation. Le nom de l’instance suit le nouveau lieu, mais **les identifiants des entités ne changent pas** : tableaux de bord, cartes et automatisations restent valides.
- **Réglages** : rayon, type de don, horizon, intervalle… (tableau ci-dessus).

L’instance se recharge automatiquement ; aucune réinstallation, aucun redémarrage.

**Localisation mobile (personne ou traceur).** Une nouvelle recherche est lancée quand l’entité s’éloigne de plus de 3 km du dernier point de recherche, au plus une fois toutes les 10 minutes, en plus du rafraîchissement régulier. Si l’entité ne publie momentanément plus de position (téléphone sans GPS, hors zone), l’instance conserve le dernier lieu connu.

### Plusieurs zones

L’intégration s’ajoute autant de fois que nécessaire : **Ajouter une intégration → EFS** à nouveau, avec un autre lieu (domicile, travail, résidence secondaire, un proche…). Chaque instance a son propre appareil, ses réglages, son calendrier et ses capteurs, nommés d’après la zone : une instance « EFS Caen » crée `sensor.efs_caen_prochaine_collecte`, `calendar.efs_caen_collectes`, etc. Un même lieu ne peut pas être surveillé par deux instances (le message « Une instance surveille déjà ce lieu » l’indique). Chaque instance interroge l’API une fois par intervalle.

---

## 4. Entités créées

| Entité | État | Usage principal |
|---|---|---|
| `sensor.efs_prochaine_collecte` | Date/heure de début (timestamp) | Affichage, carte Map grâce aux attributs `latitude`/`longitude` |
| `sensor.efs_prochaine_collecte_places_totales` | Nombre de places | Affichage « X sur Y » |
| `sensor.efs_prochaine_collecte_places_restantes` | Nombre de places, historisé | Alerte « moins de 10 places », graphique de remplissage |
| `sensor.efs_prochaine_collecte_taux_remplissage` | % historisé | Carte Jauge |
| `sensor.efs_collectes_a_venir` | Nombre de collectes dans l’horizon | Attribut `collectes` : liste compacte des N prochaines |
| `calendar.efs_collectes` | Actif pendant un créneau | Cartes Calendrier/Agenda, déclencheur « la veille » |
| `binary_sensor.efs_collecte_proche` | Actif si collecte sous X jours | Conditions d’automatisation |

Les identifiants ci-dessus sont ceux de la première instance installée avant la v1.3.0 ; les instances créées depuis portent le nom de leur zone (`sensor.efs_<zone>_prochaine_collecte`, `calendar.efs_<zone>_collectes`…). Tous restent renommables dans l’interface.

**Attributs de `sensor.efs_prochaine_collecte`** : `lieu`, `adresse`, `commune`, `code_postal`, `distance` (km), `horaires` (ex. `08h30-12h00 / 15h00-19h00`), `fin`, `creneaux`, `statut` (*Planning ouvert*, *Planning non ouvert*, *Complet*), `places_totales`, `places_restantes`, `places_reservees`, `taux_remplissage`, `places` (texte prêt à afficher), `lien_rdv`, `libelle`, `nature`, `latitude`, `longitude`, `type_don`, `api_disponible`, `derniere_mise_a_jour`.

**Chaque élément de l’attribut `collectes`** porte `date`, `debut`, `fin`, `horaires`, `lieu`, `adresse`, `commune`, `distance`, `places_totales`, `places_restantes`, `places_reservees`, `taux_remplissage`, `statut`, `lien_rdv`, `latitude` et `longitude`. Le même capteur expose aussi `instance`, `localisation` (`home`, `postal` ou `entity`), `centre` (point de recherche), `rayon_km`, `horizon_jours` et `type_don`.

**Calendrier** : un événement par créneau (une collecte matin + après-midi donne deux événements). La description reprend les places (« 39 places restantes sur 54 » ou « Planning non ouvert »), le créneau, la distance et le lien de rendez-vous.

### Règles de gestion à connaître

- **Planning non ouvert ≠ complet.** Tant que l’EFS n’a pas ouvert les rendez-vous, l’API renvoie des compteurs nuls. Les capteurs numériques passent alors à `unknown` (et non à 0, qui laisserait croire la collecte complète), le statut vaut *Planning non ouvert*. Le passage de `unknown` à une valeur signale l’ouverture du planning.
- **Taux de remplissage** : calculé à partir des compteurs du type de don choisi, `(totales − restantes) / totales`, pour rester cohérent avec les places affichées. La valeur globale fournie par l’EFS sert de repli.
- **Prochaine collecte** : une collecte en cours reste « prochaine » jusqu’à la fin de son dernier créneau, ce qui laisse le temps de s’y rendre le jour même.
- **Fuseau horaire** : toutes les dates sont construites en Europe/Paris, passage heure d’été/hiver compris.
- **Filtres de qualité** : sont écartés les lieux hors du cercle (coins du rectangle de recherche), les lieux sans collecte, les doublons et les lieux dont le code postal est incompatible avec la position (cas constaté de sites de Sophia Antipolis géolocalisés près de Caen). Les rejets sont visibles dans les diagnostics.
- **Panne de l’API** : la dernière réponse valide est conservée en mémoire et sur disque. Les entités restent disponibles avec ces données, l’attribut `api_disponible` passe à `false` et un avertissement unique est inscrit dans le journal. Le cache survit à un redémarrage.

---

## 5. Affichage

### Propositions de cartes (exemple Bretteville-sur-Odon, 10 km, 30 jours)

Les cartes 1 à 6 utilisent `custom:efs-collectes-card` (dépôt [HomeAssistant_DonduSang_Card](https://github.com/Laurent14760/HomeAssistant_DonduSang_Card), installé au § 2.5) ; la 7 n’utilise que des cartes natives. Toutes se collent par Tableau de bord → ✏️ Modifier → + Ajouter une carte → **Manuel**, et se règlent ensuite dans l’éditeur visuel.

| N° | Carte | Source des données | Usage conseillé |
|---|---|---|---|
| 1 | Vue complète de l’instance | Instance « EFS Bretteville-sur-Odon » | Tableau de bord principal |
| 2 | Prochaine collecte à Bretteville | Instance | Tablette murale, vue compacte |
| 3 | Rendez-vous disponibles | Instance | Savoir où donner cette semaine |
| 4 | Recherche propre à la carte | Code postal, rayon, type, jours | Suivre un lieu sans créer d’instance |
| 5 | Recherche libre avec formulaire | Saisie dans la carte | Tablette partagée, autre type de don |
| 6 | Uniquement la commune | Rayon 0 | Collectes dans Bretteville, sans les voisines |
| 7 | Cartes natives | Entités de l’instance | Sans carte personnalisée |

**1. Vue complète de l’instance** – prochaine collecte, agenda, plan et remplissage :

```yaml
type: custom:efs-collectes-card
entity: sensor.efs_bretteville_sur_odon_collectes_a_venir
vue: complet
titre: Don du sang – Bretteville-sur-Odon
```

**2. Prochaine collecte à Bretteville (tablette murale)** – présente la prochaine collecte *dans la commune* plutôt que la plus proche dans le temps, sans en-tête ni pied :

```yaml
type: custom:efs-collectes-card
entity: sensor.efs_bretteville_sur_odon_collectes_a_venir
vue: synthese
commune: Bretteville-sur-Odon
afficher_entete: false
afficher_pied: false
```

La carte ne voit que les collectes listées par l’instance : si celle de Bretteville n’apparaît pas, augmenter son réglage « Nombre maximum de collectes listées » (jusqu’à 30) ou utiliser la proposition 6.

**3. Rendez-vous disponibles dans les 30 jours** – agenda limité aux collectes au planning ouvert :

```yaml
type: custom:efs-collectes-card
entity: sensor.efs_bretteville_sur_odon_collectes_a_venir
vue: agenda
titre: Où donner ce mois-ci
filtre: rdv_ouverts
jours: 30
max: 8
```

**4. Recherche propre à la carte** – mêmes paramètres que l’instance, sans en dépendre (aucune entité, aucun historique) :

```yaml
type: custom:efs-collectes-card
vue: complet
titre: Collectes autour de Bretteville
code_postal: "14760"
rayon_km: 10
type_don: sang
jours: 30
```

**5. Recherche libre avec formulaire** – code postal, rayon, type de collecte et nombre de jours modifiables dans la carte ; les valeurs ci-dessous sont celles proposées à l’ouverture :

```yaml
type: custom:efs-collectes-card
vue: agenda
afficher_formulaire: true
code_postal: "14760"
rayon_km: 10
type_don: sang
jours: 30
```

**6. Uniquement la commune de Bretteville-sur-Odon** – rayon 0 : seules les collectes de la commune de départ, ici sur 60 jours pour ne pas manquer la prochaine :

```yaml
type: custom:efs-collectes-card
vue: synthese
titre: Collectes à Bretteville-sur-Odon
code_postal: "14760"
rayon_km: 0
jours: 60
```

**7. Cartes natives** – voir ci-dessous et `examples/tableau_de_bord.yaml` (remplacer `sensor.efs_…` par les identifiants de l’instance, ex. `sensor.efs_bretteville_sur_odon_…`).

Bornes communes : rayon de 0 à 50 km (1 à 50 pour une instance), nombre de jours de 1 à 180 ; une valeur hors bornes est signalée par la carte. Les réglages d’affichage (`afficher_*`, `couleur`, `max`, `distance_max`) sont détaillés dans le README de la carte.

### Action `efs_dondesang.rechercher_collectes`

Recherche à la demande, sans instance dédiée ni entité créée. Elle renvoie une réponse (`response_variable`) et peut donc aussi servir dans un script.

| Champ | Défaut | Description |
|---|---|---|
| `code_postal` | — | Point de départ (5 chiffres). À défaut : `latitude` et `longitude` |
| `commune` | 1re par ordre alphabétique | Nom ou code INSEE, pour un code postal couvrant plusieurs communes |
| `rayon_km` | 10 | 0 à 50 km ; **0 = uniquement la commune de départ** (recherche à 10 km puis filtre sur le nom de la commune ; code postal requis) |
| `type_don` | `sang` | `sang`, `plasma`, `plaquettes` |
| `jours` | 30 | 1 à 180 jours à partir d’aujourd’hui |
| `inclure_professionnelles` | `false` | Collectes en entreprise ou établissement scolaire |
| `max_collectes` | 30 | 1 à 100 (la réponse n’est pas historisée, la limite de 16 Ko ne s’applique pas) |

La réponse reprend le format des attributs de `collectes_a_venir` : `perimetre` (`rayon` ou `commune`), `centre` (libellé, code postal, code INSEE, coordonnées), `communes` (communes du code postal), `rayon_km`, `type_don`, `horizon_jours`, `nombre` (total avant troncature), `collectes`, `maisons_du_don`, `derniere_mise_a_jour`, `api_disponible`, `source` (`api` ou `cache`).

```yaml
action: efs_dondesang.rechercher_collectes
data:
  code_postal: "14400"
  rayon_km: 15
  type_don: plasma
  jours: 45
response_variable: recherche
```

Les filtres (type de don, nombre de jours, collectes professionnelles) sont appliqués sur une réponse brute de l’EFS mise en cache 15 minutes par zone ; les communes d’un code postal le sont 24 heures. En cas de panne, la dernière réponse connue pour la zone est renvoyée avec `api_disponible: false`. L’action est déclarée dès que l’intégration est chargée : au moins une instance doit être installée.

> La version 1.1.0 de l’intégration embarquait cette carte ; depuis la 1.2.0 elle ne l’embarque plus. Après la mise à jour, supprimez toute ressource de tableau de bord pointant vers `/efs_dondesang/efs-collectes-card.js`.

### Cartes natives

Le fichier `examples/tableau_de_bord.yaml` contient une pile de cartes prête à coller, écrite pour la première instance (`sensor.efs_…`) : adapter les identifiants à votre instance (Tableau de bord → ⋮ → Modifier → Ajouter une carte → Manuel). Elle combine :

- une carte **Markdown** de synthèse :

```jinja
{% set e = 'sensor.efs_prochaine_collecte' %}
{% set r = states('sensor.efs_prochaine_collecte_places_restantes') %}
{% set t = states('sensor.efs_prochaine_collecte_places_totales') %}
{% set lien = state_attr(e, 'lien_rdv') %}
{% if states(e) in ['unknown', 'unavailable'] %}
Aucune collecte dans l'horizon configuré.
{% else %}
Prochaine collecte : **{{ state_attr(e, 'lieu') }}** ({{ state_attr(e, 'commune') }}, {{ state_attr(e, 'distance') }} km)
{{ as_timestamp(states(e)) | timestamp_custom('%d/%m') }} · {{ state_attr(e, 'horaires') }}

{{ 'Planning non ouvert' if r in ['unknown', 'unavailable'] else r ~ ' places restantes sur ' ~ t }}{% if lien %} · [Prendre RDV]({{ lien }}){% endif %}
{% endif %}
```

- une carte **Jauge** sur `sensor.efs_prochaine_collecte_taux_remplissage` (vert, orange, rouge) ;
- une carte **Carte** (Map) sur `sensor.efs_prochaine_collecte` ;
- une carte **Agenda** sur `calendar.efs_collectes`.

Note : le filtre `timestamp_custom('%A …')` affiche le jour de la semaine en anglais, Jinja ne connaissant pas la locale française. Le modèle ci-dessus s’en tient donc à la date numérique.

---

## 6. Automatisations

Le fichier `examples/automatisations.yaml` fournit trois automatisations à importer (Paramètres → Automatisations → Créer → ⋮ → Modifier en YAML). Remplacer `notify.notify` par votre service de notification mobile (`notify.mobile_app_…`).

1. **Rappel la veille** : déclencheur Calendrier 12 h avant le début d’un événement de `calendar.efs_collectes`.
2. **Places bientôt épuisées** : déclencheur Numérique quand `…_places_restantes` passe sous 10.
3. **Ouverture du planning** : `…_places_restantes` quitte l’état `unknown`.

---

## 7. Vérification après installation (recette)

| Contrôle | Résultat attendu |
|---|---|
| Ajout avec code postal 14760, rayon 10 km | Commune Bretteville-sur-Odon retenue, entités créées |
| `sensor.efs_collectes_a_venir`, attribut `collectes` | Collectes de Bretteville-sur-Odon et des communes voisines (Fontaine-Étoupefour, Bretteville-l’Orgueilleuse, Caen…), triées par date, toutes à ≤ 10 km |
| Comparaison avec dondesang.efs.sante.fr | Places identiques, au délai de rafraîchissement près |
| Collecte au planning fermé | Capteurs numériques `unknown`, calendrier « Planning non ouvert » |
| Options → type de don « Plasma » | Places et lien basculent sur les compteurs plasma |
| Diagnostics (⋮ sur l’intégration → Télécharger les diagnostics) | Aucun lieu aberrant dans `collectes`, motifs listés dans `rejets` |
| Coupure réseau simulée | Entités inchangées, `api_disponible: false`, un avertissement au journal |

Remarque sur l’horizon : il se compte à partir d’aujourd’hui. Au 14 octobre, un horizon de 60 jours s’arrête au 13 décembre ; la collecte du 14 décembre apparaîtra le lendemain ou en portant l’horizon à 61 jours ou plus.

---

## 8. Dépannage

- **L’intégration n’apparaît pas dans la liste** : vérifier le chemin `/config/custom_components/efs_dondesang/manifest.json`, redémarrer, vider le cache du navigateur.
- **« Échec de la configuration, nouvelle tentative »** : l’API EFS ne répond pas et aucun cache n’existe encore (premier démarrage). Home Assistant réessaie automatiquement.
- **Aucune collecte** : élargir le rayon ou l’horizon ; vérifier dans les diagnostics `nb_lieux_bruts` (réponse de l’API) et `rejets` (lieux écartés et motif).
- **Journalisation détaillée** : sur la page de l’intégration, ⋮ → *Activer la journalisation de débogage*, attendre un rafraîchissement, puis désactiver pour télécharger le journal.

---

## 9. Tests

```bash
pip install -r requirements_test.txt
pytest
```

Les tests portent sur la logique métier (`parser.py`, `search.py`), indépendante de Home Assistant, à partir de réponses JSON enregistrées dans `tests/fixtures/` : conversion rayon/rectangle, haversine, filtre au cercle, cohérence code postal, collectes professionnelles, créneaux nuls ou au format datetime, planning non ouvert, collecte complète, bascule de type de don, doublons, horizon, taille de l’attribut `collectes` ; pour l’action de recherche : choix de la commune d’un code postal, cache (fraîcheur, repli, éviction), format et troncature de la réponse.

---

## 10. Limites et précautions

- L’API Carto v3 est publique mais sans engagement de service formel ; son format peut évoluer. Les diagnostics incluent un extrait de la réponse brute pour faciliter l’adaptation.
- Les jeux de test reproduisent la structure décrite dans la spécification ; un premier contrôle sur la réponse réelle (via les diagnostics) est recommandé lors de la mise en service.
- La classification « professionnelle » repose sur le champ `nature` (mots-clés : professionnel, entreprise, lycée, collège, école, université, administration…). Une nouvelle valeur inconnue sera traitée comme publique.

Sources des données : [data.gouv.fr – Lieux et horaires des collectes de sang (EFS)](https://www.data.gouv.fr/), [API Géo](https://geo.api.gouv.fr/), [lou-dupont/EFS](https://github.com/lou-dupont/EFS).
