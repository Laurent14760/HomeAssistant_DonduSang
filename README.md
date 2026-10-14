# EFS – Collectes de don du sang pour Home Assistant

Intégration personnalisée qui interroge l’API Carto v3 publique de l’Établissement français du sang (EFS) et expose les prochaines collectes autour d’une commune ou du domicile : date, lieu, horaires, places totales et restantes, taux de remplissage et lien de prise de rendez-vous. Les données alimentent des capteurs, un calendrier et un capteur binaire, utilisables tels quels dans les tableaux de bord et les automatisations.

| Élément | Valeur |
|---|---|
| Domaine | `efs_dondesang` |
| Version | 1.2.0 |
| Home Assistant minimum | 2024.11 |
| Classe IoT | `cloud_polling` (1 appel par instance et par intervalle) |
| Dépendances Python | aucune (aiohttp fourni par Home Assistant) |
| Configuration | 100 % interface, aucune ligne de YAML |

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
│   ├── diagnostics.py
│   ├── manifest.json, strings.json
│   └── translations/fr.json, en.json
├── examples/
│   ├── tableau_de_bord.yaml          cartes Markdown, Jauge, Carte, Agenda
│   └── automatisations.yaml          veille de collecte, places, ouverture du planning
└── tests/                            pytest sur réponses JSON enregistrées
```

---

## 2. Installation

### Option A – via HACS (recommandée)

HACS installe une intégration depuis un dépôt GitHub. Il faut donc publier le package une fois :

1. Créer un dépôt GitHub (public ou privé accessible à HACS), par exemple `efs_dondesang`, et y pousser le contenu du zip **à la racine** (le fichier `hacs.json` et le dossier `custom_components/` doivent être au premier niveau).
2. Mettre à jour dans `custom_components/efs_dondesang/manifest.json` les champs `documentation`, `issue_tracker` et `codeowners` avec l’adresse réelle du dépôt et votre identifiant GitHub.
3. Facultatif mais conseillé : créer une *release* GitHub `v1.0.0`. HACS proposera alors les mises à jour à chaque nouvelle release.
4. Dans Home Assistant : **HACS → ⋮ → Dépôts personnalisés**, saisir l’URL du dépôt, catégorie **Intégration**, puis **Ajouter**.
5. Rechercher « EFS – Collectes de don du sang » dans HACS, cliquer **Télécharger**.
6. **Redémarrer Home Assistant** (Paramètres → Système → ⏻ → Redémarrer).

### Option B – installation manuelle

1. Décompresser le zip.
2. Copier le dossier `custom_components/efs_dondesang` dans le dossier `/config/custom_components/` de Home Assistant (créer `custom_components` s’il n’existe pas). Les modules complémentaires *Samba share*, *Studio Code Server* ou *Advanced SSH & Web Terminal* permettent d’accéder à `/config`.
3. Vérifier l’arborescence finale : `/config/custom_components/efs_dondesang/manifest.json` doit exister.
4. Redémarrer Home Assistant.

L’installation manuelle ne bénéficie pas des notifications de mise à jour HACS : il faut recopier le dossier à chaque nouvelle version.

---

## 3. Configuration

**Paramètres → Appareils et services → Ajouter une intégration → « EFS »**

L’assistant propose deux points de référence :

- **Utiliser la position de la maison** : reprend la position définie dans Paramètres → Système → Général. C’est le cas le plus courant, sans saisie.
- **Saisir un code postal** : la commune est résolue par l’API Géo de l’État (`geo.api.gouv.fr`). Si le code postal couvre plusieurs communes (cas fréquent en zone rurale), un écran permet de choisir la bonne ; son centre géographique devient le point de recherche.

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

Tous ces réglages restent modifiables ensuite via **Configurer** sur la carte de l’intégration ; l’instance se recharge automatiquement.

**Plusieurs instances** : on peut ajouter l’intégration une seconde fois (par exemple domicile et lieu de travail). Une même localisation ne peut pas être configurée deux fois.

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

Une seconde instance reçoit des identifiants suffixés `_2` (`sensor.efs_prochaine_collecte_2`…), renommables dans l’interface.

**Attributs de `sensor.efs_prochaine_collecte`** : `lieu`, `adresse`, `commune`, `code_postal`, `distance` (km), `horaires` (ex. `08h30-12h00 / 15h00-19h00`), `fin`, `creneaux`, `statut` (*Planning ouvert*, *Planning non ouvert*, *Complet*), `places_totales`, `places_restantes`, `places_reservees`, `taux_remplissage`, `places` (texte prêt à afficher), `lien_rdv`, `libelle`, `nature`, `latitude`, `longitude`, `type_don`, `api_disponible`, `derniere_mise_a_jour`.

**Chaque élément de l’attribut `collectes`** porte `date`, `debut`, `horaires`, `lieu`, `commune`, `distance`, `places_totales`, `places_restantes`, `places_reservees` et `lien_rdv`.

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

### Carte dédiée `custom:efs-collectes-card`

Les trois visuels (prochaine collecte, agenda, carte et remplissage) sont fournis par une carte Lovelace distribuée séparément : [HomeAssistant_DonduSang_Card](https://github.com/LoloPicolo/HomeAssistant_DonduSang_Card), à ajouter dans HACS comme dépôt personnalisé de catégorie **Tableau de bord**. Elle nécessite cette intégration en version 1.1.0 ou plus.

```yaml
type: custom:efs-collectes-card
vue: synthese            # synthese | agenda | carte | complet
```

> La version 1.1.0 de l’intégration embarquait cette carte ; depuis la 1.2.0 elle ne l’embarque plus. Après la mise à jour, supprimez toute ressource de tableau de bord pointant vers `/efs_dondesang/efs-collectes-card.js`.

### Cartes natives

Le fichier `examples/tableau_de_bord.yaml` contient une pile de cartes prête à coller (Tableau de bord → ⋮ → Modifier → Ajouter une carte → Manuel). Elle combine :

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

Les tests portent sur la logique métier (`parser.py`), indépendante de Home Assistant, à partir de réponses JSON enregistrées dans `tests/fixtures/` : conversion rayon/rectangle, haversine, filtre au cercle, cohérence code postal, collectes professionnelles, créneaux nuls ou au format datetime, planning non ouvert, collecte complète, bascule de type de don, doublons, horizon, taille de l’attribut `collectes`.

---

## 10. Limites et précautions

- L’API Carto v3 est publique mais sans engagement de service formel ; son format peut évoluer. Les diagnostics incluent un extrait de la réponse brute pour faciliter l’adaptation.
- Les jeux de test reproduisent la structure décrite dans la spécification ; un premier contrôle sur la réponse réelle (via les diagnostics) est recommandé lors de la mise en service.
- La classification « professionnelle » repose sur le champ `nature` (mots-clés : professionnel, entreprise, lycée, collège, école, université, administration…). Une nouvelle valeur inconnue sera traitée comme publique.

Sources des données : [data.gouv.fr – Lieux et horaires des collectes de sang (EFS)](https://www.data.gouv.fr/), [API Géo](https://geo.api.gouv.fr/), [lou-dupont/EFS](https://github.com/lou-dupont/EFS).
