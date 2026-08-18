# Rapport — TP Machine Learning Avancé
## Réception des relevés Klaxo-3

Ce rapport présente le chargement, la préparation et la modélisation des relevés d'observations reçus par la sonde Klaxo-3.

---

## Synthèse de la phase 1

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

## Synthèse de la phase 2

Les colonnes `duration_seconds`, `latitude` et `longitude` ont été converties en valeurs numériques. Les colonnes `datetime` et `date_posted` ont été converties en dates.

Aucune ligne n'a été supprimée : les valeurs présentes mais invalides ont été converties en `NaN` ou `NaT`.

Les fichiers `resume_conversions.csv` et `anomalies_conversion.csv` contiennent le détail des échecs de conversion.

## Synthèse de la phase 3

### Règle utilisée

Un relevé est étiqueté comme canular lorsque son commentaire contient au moins un des mots-clés suivants `hoax`, `fake`, `prank`, `joke`, `not real`, `made up` ou `fraud`.

### Résultats

| Indicateur | Valeur |
|---|---:|
| Nombre total de relevés analysés | 88679 |
| Nombre de relevés étiquetés comme canulars | 869 |
| Proportion de canulars | 0,98 % |

### Limites

Cette cible est une pseudo-étiquette et non une vérité terrain. La règle peut manquer des canulars ne contenant aucun des mots-clés retenus. Elle peut aussi marquer à tort certains commentaires : par exemple, un témoignage peut mentionner une vidéo `fake`, une `joke` ou l'avis d'une autre personne sans affirmer que le signalement est inventé.

La colonne `comments` a servi à fabriquer la cible `is_hoax`. Elle ne devra donc pas être utilisée comme variable d'entrée dans le modèle final : sinon, le modèle utiliserait indirectement l'information ayant servi à produire la réponse, ce qui créerait une fuite de données.

## Synthèse de la phase 4

Un modèle de régression logistique a été entraîné pour prédire la variable`is_hoax`. Les données ont été séparées aléatoirement en deux parties avec une
graine fixée à 42 :

- Jeu d'entraînement : 70943 relevés, soit 80 % des données.
- Jeu de test : 17736 relevés, soit 20 % des données.

Le jeu de test a été mis de côté avant l'entraînement. Il n'a donc pas été vupar le modèle pendant son apprentissage.

| Indicateur sur le jeu de test | Valeur |
|---|---:|
| Precision | 1.65% |
| Recall | 64.37% |
| Accuracy | 62.07% |

Sur 100 canulars réellement présents dans le jeu de test, le modèle en détecteenviron XX. Sur 100 relevés signalés comme canulars par le modèle, environ XX sont effectivement étiquetés comme canulars selon la règle définie à la phase 3.

> Ce résultat est provisoire. Le modèle utilise la colonne `comments`, alors que
> la cible `is_hoax` a été construite avec cette même colonne. Cette situation
> sera contrôlée et corrigée dans la phase 5.

## Synthèse de la phase 5

### Audit des informations utilisées

Le modèle initial utilisait notamment le texte du commentaire. Or la cible `is_hoax` a été construite à partir de mots-clés présents dans ce même champ. Le commentaire a donc été retiré du modèle final, ainsi que les colonnes qui en dérivent.

La colonne `date_posted` a aussi été retirée car elle est renseignée après le dépôt du signalement. Elle n'est donc pas garantie au moment où le système doit prédire la classe d'un nouveau relevé.

### Comparaison des résultats

| Version du modèle | Precision | Recall | Accuracy |
|---|---:|---:|---:|
| Avec fuite | 1.65% | 64.37% | 62.07% |
| Sans fuite | 1.69% | 42.53% | 75.13% |

Le premier modèle obtenait ses résultats en utilisant des informations déjà liées à la réponse : la cible était produite à partir du commentaire, et le modèle recevait ce commentaire en entrée. Il ne s'agissait donc pas d'une prédiction réaliste, mais d'une recherche indirecte des mots-clés ayant défini l'étiquette.

Après retrait du commentaire et de la date de publication, le modèle utilise uniquement des informations supposées disponibles lors de la réception du signalement. Les métriques obtenues après ce retrait sont donc plus crédibles, même si elles sont moins élevées.

## Synthèse de la phase 6

Le modèle du stagiaire prédit toujours « pas canular », quelle que soit
l'information disponible dans le relevé.

| Système | Accuracy | Precision sur la classe canular | Recall sur la classe canular |
|---|---:|---:|---:|
| Stagiaire : toujours non-canular | 99.02 % | 0,00 % | 0,00 % |
| Modèle sans fuite | 75.13% | 1.69% | 42.53% |

L'accuracy seule ne permet pas d'évaluer correctement ce problème, car les canulars représentent une minorité des relevés. Le stagiaire peut donc obtenir une accuracy élevée en prédisant uniquement la classe majoritaire, tout en ne détectant aucun canular.

La mesure principale présentée au Conseil est le recall de la classe « canular ». Il mesure, parmi tous les canulars réellement présents, combien sont détectés. La precision reste également indispensable : elle indique la fiabilité des alertes et évite de mobiliser inutilement les analystes sur trop
de faux positifs.