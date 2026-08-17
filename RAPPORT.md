# Rapport — TP Machine Learning Avancé
## Réception des relevés Klaxo-3

Ce rapport présente le chargement, la préparation et la modélisation des relevés d'observations reçus par la sonde Klaxo-3.

---

## Phase 1 — Ouvrir la caisse

Le fichier source ne contient pas d'en-têtes. Les 11 colonnes ont donc été nommées à partir du manifeste fourni dans le sujet. Chaque ligne a été contrôlée avant son intégration au jeu de données principal.

| Indicateur | Valeur |
|---|---:|
| Nombre de lignes physiques dans le fichier | 88875 |
| Nombre de lignes chargées dans le DataFrame principal | 88679 |
| Nombre de lignes isolées et traitées à part | 196 |

La vérification suivante est respectée : `lignes chargées + lignes isolées = lignes physiques`, soit `88679 + 196 = 88875`.

### Ligne problématique

La ligne 877 contient 12 champs, alors que le manifeste prévoit exactement 11 colonnes. Elle contient plusieurs valeurs vides avant un commentaire éditorial, ce qui provoque un décalage des champs.

Si elle était intégrée directement, le commentaire serait interprété comme une date de publication, la date de publication comme une latitude et une valeur supplémentaire resterait sans colonne associée. La ligne a été conservée dans le fichier des lignes problématiques, mais elle n'a pas été intégrée au DataFrame principal car sa structure ne permet pas une affectation fiable des valeurs aux 11 colonnes.

## Phase 2

Les colonnes `duration_seconds`, `latitude` et `longitude` ont été converties
en valeurs numériques. Les colonnes `datetime` et `date_posted` ont été
converties en dates.

Aucune ligne n'a été supprimée : les valeurs présentes mais invalides ont été
converties en `NaN` ou `NaT`.

Les anomalies observées comprennent :
1. [Anomalie réelle 1] : [nombre] occurrences.
2. [Anomalie réelle 2] : [nombre] occurrences.
3. [Anomalie réelle 3] : [nombre] occurrences.
4. [Anomalie réelle 4] : [nombre] occurrences.

Les fichiers `resume_conversions.csv` et `anomalies_conversion.csv` contiennent
le détail des échecs de conversion.