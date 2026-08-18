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

## Phase 7 — Plusieurs témoins, un seul événement

### Règle de regroupement

Deux relevés sont considérés comme appartenant au même événement lorsqu'ils ont la même date et heure d'observation (`datetime`), la même ville (`city`), le même État ou région (`state`) et le même pays (`country`).

Cette règle crée un identifiant d'événement à partir de ces quatre colonnes. Les valeurs manquantes sont remplacées par la valeur technique `<MANQUANT>` afin de ne pas perdre de lignes lors du regroupement.

### Événements avec plusieurs témoins

| Indicateur | Valeur |
|---|---:|
| Événements signalés par plus d'un témoin | 1 102 |
| Nombre de témoins du plus grand événement | 19 |
| Événements répartis entre train et test avec la découpe aléatoire | 373 |
| Relevés appartenant à ces événements à cheval | 889 |

Le plus grand événement correspond à des observations effectuées à Tinley Park, dans l'Illinois, le 31 octobre 2004 à 20 h. Les 19 témoignages décrivent principalement des lumières rouges ou orange dans le ciel et sont tous associés au même événement selon la règle retenue.

La découpe aléatoire séparait 889 relevés appartenant à 373 événements entre l'apprentissage et le test. Le modèle pouvait donc être évalué sur des témoignages décrivant un événement dont il avait déjà vu d'autres versions pendant l'entraînement.

### Témoignages identiques

| Indicateur | Valeur |
|---|---:|
| Groupes de commentaires identiques | 318 |
| Lignes appartenant à ces groupes | 885 |
| Doublons supplémentaires après la première occurrence | 567 |

Les témoignages identiques ont été conservés : un même texte peut correspondre à plusieurs signalements, ou à plusieurs témoins. Ils ne sont pas supprimés automatiquement afin de ne pas perdre de données. En revanche, le regroupement par événement évite qu'un même événement soit réparti entre le jeu
d'apprentissage et le jeu de test.

Le fichier contient aussi des commentaires identiques associés à des événements différents, par exemple des commentaires standardisés de type `NUFORC Note` ou des descriptions très courtes comme `2 bright lights`. L'identité textuelle seule ne suffit donc pas à définir un événement : les colonnes de date et de localisation restent nécessaires.

### Impact de la découpe

| Découpage | Precision | Recall |
|---|---:|---:|
| Découpage aléatoire | 1,69 % | 42,53 % |
| Découpage par événements | 1,27 % | 49,39 % |

Avec la découpe par événements, la precision diminue de 1,69 % à 1,27 %, tandis que le recall augmente de 42,53 % à 49,39 %. Les métriques changent parce que le jeu de test ne contient plus de témoignages relatifs à des événements déjà vus pendant l'apprentissage. Cette évaluation est donc plus honnête, même si
la precision reste très faible.

La vérification effectuée avec `GroupShuffleSplit` confirme qu'aucun identifiant d'événement n'est présent à la fois dans le jeu d'entraînement et dans le jeu de test.

## Phase 8 — L'ordre des choses

### Choix de la date de découpe

La découpe temporelle a été réalisée avec la colonne `datetime`, qui correspond
à la date et à l'heure de l'observation déclarée par le témoin. Ce choix permet
d'entraîner le modèle sur des événements anciens, puis de l'évaluer sur des
observations réellement plus récentes.

La colonne `date_posted` n'a pas été utilisée, car elle correspond à la date de
publication ou de traitement du dossier par le Bureau. Elle ne représente pas
le moment où le phénomène a été observé.

Les 1 220 relevés sans valeur dans `datetime` ont été conservés dans les données
globales, mais ils ne peuvent pas être positionnés dans le temps et ne sont donc
pas utilisés pour cette évaluation temporelle. 

### Découpage temporel

La date de coupure retenue est le **17 janvier 2012 à 18 h 00**. Toutes les
observations du jeu d'entraînement sont antérieures à cette date, tandis que
toutes les observations du jeu de test sont égales ou postérieures à cette
date. 

| Indicateur | Jeu d'entraînement | Jeu de test |
|---|---:|---:|
| Nombre de relevés | 69 967 | 17 492 |
| Nombre de canulars | 686 | 138 |
| Proportion de canulars | 0,98 % | 0,79 % |
| Première date | 11 novembre 1906 | 17 janvier 2012 |
| Dernière date | 17 janvier 2012 à 17 h 35 | 8 mai 2014 à 18 h 45 |

La dernière observation du jeu d'entraînement, datée du 17 janvier 2012 à
17 h 35, est strictement antérieure à la première observation du jeu de test,
datée du 17 janvier 2012 à 18 h 00. La contrainte temporelle est donc
respectée. 

La proportion de canulars diminue de 0,98 % dans les données anciennes à 0,79 %
dans les données récentes. La classe positive est donc légèrement moins
fréquente dans le jeu de test, ce qui peut modifier les performances observées
et rend la precision particulièrement difficile à obtenir.

### Résultats du modèle

| Indicateur sur le jeu de test temporel | Valeur |
|---|---:|
| Precision | 1,25 % |
| Recall | 48,55 % |
| Accuracy | 69,45 % |

Sur les 138 canulars présents dans la période récente, le modèle en détecte 67
et en manque 71. Parmi les 5 340 relevés signalés comme canulars, seuls 67 sont
effectivement étiquetés comme tels par la règle retenue ; le modèle produit donc
un grand nombre de faux positifs. 

### Évolution par rapport à la phase 7

| Évaluation | Precision | Recall |
|---|---:|---:|
| Phase 7 — Découpage par événements | 1,27 % | 49,39 % |
| Phase 8 — Découpage temporel | 1,25 % | 48,55 % |

Le passage à une évaluation temporelle fait légèrement diminuer la precision et
le recall. Cette baisse est attendue : le modèle est maintenant évalué sur une
période plus récente, dont il n'a pas pu observer les signalements pendant son
apprentissage. Les résultats de la phase 8 sont donc plus représentatifs du
fonctionnement réel du système sur de futures transmissions.

## Phase 9 — Les cases vides

### Colonnes étudiées

Les trois colonnes les plus incomplètes sont `country`, `state` et
`duration_hours_min`.

| Colonne | Nombre de valeurs manquantes | Proportion de valeurs manquantes |
|---|---:|---:|
| `country` | 12 365 | 13,94 % |
| `state` | 7 409 | 8,35 % |
| `duration_hours_min` | 3 017 | 3,40 % |

La colonne `shape` contient également 2 922 valeurs manquantes, soit 3,30 %,
mais elle arrive après les trois colonnes retenues pour l'analyse. 

### Lien entre les cases vides et les canulars

| Colonne | Canulars si valeur manquante | Canulars si valeur présente | Écart |
|---|---:|---:|---:|
| `country` | 1,213 % | 0,942 % | +0,271 point |
| `state` | 1,390 % | 0,943 % | +0,447 point |
| `duration_hours_min` | 2,618 % | 0,922 % | +1,696 point |

Les trois colonnes étudiées montrent une proportion de canulars plus élevée
lorsque la valeur est absente. L'écart est particulièrement important pour
`duration_hours_min` : les relevés sans durée écrite par le témoin contiennent
2,618 % de canulars, contre 0,922 % lorsque cette durée est renseignée. Une
valeur manquante contient donc une information potentiellement utile pour la
prédiction et ne doit pas être simplement effacée.

### Traitement retenu

Les valeurs numériques manquantes sont remplacées par la médiane, calculée
uniquement à partir du jeu d'entraînement. Les valeurs textuelles manquantes
sont représentées par la catégorie `<MANQUANT>`.

Trois indicateurs binaires ont été ajoutés :

- `country_etait_manquant`
- `state_etait_manquant`
- `duration_hours_min_etait_manquant`

Chaque indicateur vaut 1 si la valeur d'origine était manquante et 0 sinon.
Cette méthode permet de compléter les données pour que le modèle puisse les
traiter, tout en conservant explicitement la trace de l'absence initiale. Les
médianes et le vocabulaire textuel sont appris dans le pipeline sur le jeu
d'entraînement uniquement, ce qui évite d'utiliser des informations du jeu de
test.

### Résultats du modèle

La découpe temporelle est conservée : le modèle apprend sur 69 967 relevés
antérieurs au 17 janvier 2012 à 18 h 00, puis il est évalué sur 17 492 relevés
plus récents.

| Indicateur sur le jeu de test temporel | Valeur |
|---|---:|
| Precision | 1,42 % |
| Recall | 59,42 % |
| Accuracy | 67,25 % |

La matrice de confusion indique que le modèle détecte 82 des 138 canulars du
jeu de test, mais manque encore 56 canulars. Il déclenche aussi 5 673 faux
positifs : beaucoup de relevés non étiquetés comme canulars sont signalés à
tort. 

Par rapport à la phase 8, le recall passe de 48,55 % à 59,42 %, tandis que la
precision passe de 1,25 % à 1,42 %. L'ajout des indicateurs de valeurs
manquantes améliore donc la détection des canulars selon la règle retenue, même
si le nombre de fausses alertes reste très élevé. 