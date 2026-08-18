"""
TP Machine Learning Avancé — Réception des relevés Klaxo-3

Ce script exécute l'ensemble de l'analyse de manière reproductible :

1. Téléchargement du fichier source s'il n'existe pas.
2. Chargement robuste des lignes CSV :
   - les lignes à 11 colonnes sont chargées ;
   - les lignes ayant un autre nombre de colonnes sont isolées ;
   - aucune ligne ne disparaît silencieusement.
3. Conversion des dates, coordonnées et durées.
4. Détection et export des anomalies.
5. Création de la cible artificielle is_hoax (« canular »).
6. Entraînement d'un premier modèle volontairement avec fuite de données.
7. Construction d'un modèle sans fuite de données.
8. Comparaison avec le modèle naïf du stagiaire qui répond toujours
   « pas canular ».
9. Export des résultats dans outputs/resultats_analyse/.

Exécution :
    python analyse.py
"""

from pathlib import Path
import csv
import re
import urllib.request

import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


# ============================================================================
# 1. CONFIGURATION GÉNÉRALE
# ============================================================================

# URL fournie dans le sujet. Le fichier source ne contient pas les en-têtes.
URL_DATA = (
    "https://raw.githubusercontent.com/planetsig/ufo-reports/master/"
    "csv-data/ufo-complete-geocoded-time-standardized.csv"
)

# Les 11 colonnes attendues, dans le même ordre que celui du manifeste.
COLUMNS = [
    "datetime",
    "city",
    "state",
    "country",
    "shape",
    "duration_seconds",
    "duration_hours_min",
    "comments",
    "date_posted",
    "latitude",
    "longitude",
]

# Colonnes qui doivent devenir numériques.
NUMERIC_COLUMNS = [
    "duration_seconds",
    "latitude",
    "longitude",
]

# Colonnes qui doivent devenir des dates.
DATE_COLUMNS = [
    "datetime",
    "date_posted",
]

# Mots ou expressions utilisés pour fabriquer la cible artificielle is_hoax.
# Un relevé est marqué canular si son commentaire contient au moins un de ces
# mots-clés, sans tenir compte des majuscules ou minuscules.
HOAX_KEYWORDS = [
    "hoax",
    "fake",
    "prank",
    "joke",
    "not real",
    "made up",
    "fraud",
]

# Graine utilisée pour rendre le découpage train/test reproductible.
RANDOM_STATE = 42

# 20 % des données sont conservées pour le test final.
TEST_SIZE = 0.20


# ============================================================================
# 2. TÉLÉCHARGEMENT ET CHARGEMENT ROBUSTE — PHASE 1
# ============================================================================

def download_data(data_path: Path) -> None:
    """
    Télécharge le fichier CSV si celui-ci n'existe pas encore.

    Le téléchargement est automatique afin que le script fonctionne dans un
    dossier nouvellement cloné, sans que l'utilisateur ait à déposer le CSV
    manuellement dans data/.
    """
    if data_path.exists():
        print(f"Le fichier source existe déjà : {data_path}")
        return

    print("Téléchargement du fichier source...")
    urllib.request.urlretrieve(URL_DATA, data_path)
    print("Téléchargement terminé.")


def load_data_robustly(data_path: Path):
    """
    Charge le fichier CSV sans perdre silencieusement les lignes mal formées.

    Une ligne est considérée comme valide si elle contient exactement 11 champs,
    ce qui correspond au manifeste fourni par le sujet.

    Les lignes ayant moins ou plus de 11 champs ne sont pas supprimées :
    elles sont conservées dans un DataFrame séparé avec leur numéro de ligne,
    leur nombre de champs et leur contenu brut.

    Returns
    -------
    dataframe : pandas.DataFrame
        Lignes CSV ayant exactement 11 champs.
    dataframe_bad_rows : pandas.DataFrame
        Lignes ayant une structure différente de 11 champs.
    total_physical_rows : int
        Nombre de lignes physiques présentes dans le fichier.
    """
    valid_rows = []
    bad_rows = []

    # errors="replace" évite l'arrêt du script si un caractère est encodé de
    # manière inattendue. newline="" permet au module csv de gérer correctement
    # les fins de lignes.
    with open(
        data_path,
        "r",
        encoding="utf-8",
        errors="replace",
        newline=""
    ) as file:
        reader = csv.reader(file)

        for line_number, row in enumerate(reader, start=1):
            # Le fichier doit respecter 11 colonnes.
            if len(row) == len(COLUMNS):
                valid_rows.append(row)
            else:
                # La ligne est conservée dans les résultats afin de pouvoir
                # expliquer précisément pourquoi elle n'est pas dans df.
                bad_rows.append(
                    {
                        "numero_ligne": line_number,
                        "nombre_champs": len(row),
                        "contenu_brut": repr(row),
                    }
                )

    # Création du DataFrame principal avec les en-têtes du manifeste.
    dataframe = pd.DataFrame(valid_rows, columns=COLUMNS)

    # DataFrame séparé des anomalies de structure.
    dataframe_bad_rows = pd.DataFrame(bad_rows)

    # Compte des lignes physiques : cela permet de vérifier que
    # lignes chargées + lignes isolées = lignes totales.
    with open(
        data_path,
        "r",
        encoding="utf-8",
        errors="replace"
    ) as file:
        total_physical_rows = sum(1 for _ in file)

    return dataframe, dataframe_bad_rows, total_physical_rows


# ============================================================================
# 3. CONVERSION DES TYPES ET ANALYSE DES ANOMALIES — PHASE 2
# ============================================================================

def convert_types(dataframe: pd.DataFrame):
    """
    Convertit les colonnes dans leurs types attendus sans supprimer de lignes.

    - duration_seconds, latitude et longitude deviennent des nombres ;
    - datetime et date_posted deviennent des dates ;
    - les valeurs non convertibles deviennent NaN ou NaT ;
    - les valeurs originales qui ont échoué à la conversion sont enregistrées.

    Une valeur vide à l'origine n'est pas classée comme un échec de conversion :
    elle est considérée comme absente dans la transmission. Un échec correspond
    à une valeur présente, mais incompatible avec le type attendu.

    Returns
    -------
    dataframe : pandas.DataFrame
        DataFrame avec les colonnes converties.
    dataframe_conversion_issues : pandas.DataFrame
        Détail des valeurs présentes mais non convertibles.
    """
    # On copie les données afin de préserver le DataFrame initial.
    dataframe = dataframe.copy()

    # Cette copie est essentielle pour afficher les valeurs fautives d'origine
    # après que pandas les a remplacées par NaN ou NaT.
    dataframe_before_conversion = dataframe.copy()

    conversion_issues = []

    # Conversion des nombres.
    # errors="coerce" remplace les valeurs invalides par NaN sans supprimer
    # leur ligne ni arrêter le programme.
    for column in NUMERIC_COLUMNS:
        dataframe[column] = pd.to_numeric(
            dataframe[column],
            errors="coerce"
        )

    # Conversion des dates.
    # Une date invalide devient NaT, mais la ligne est conservée.
    for column in DATE_COLUMNS:
        dataframe[column] = pd.to_datetime(
            dataframe[column],
            errors="coerce"
        )

    # Recherche des échecs de conversion, colonne par colonne.
    for column in NUMERIC_COLUMNS + DATE_COLUMNS:
        # Les valeurs originales sont normalisées en texte et les espaces
        # inutiles sont retirés.
        original_values = (
            dataframe_before_conversion[column]
            .astype("string")
            .str.strip()
        )

        # Une valeur compte comme "présente" si elle n'est ni manquante ni vide.
        value_was_provided = (
            original_values.notna()
            & original_values.ne("")
        )

        # Une conversion a échoué si une valeur était présente avant, mais est
        # devenue manquante après conversion.
        conversion_failed = (
            value_was_provided
            & dataframe[column].isna()
        )

        # Enregistrement détaillé de chaque valeur non convertible.
        for row_index, original_value in original_values[
            conversion_failed
        ].items():
            conversion_issues.append(
                {
                    "index_dataframe": row_index,
                    "colonne": column,
                    "valeur_originale": original_value,
                }
            )

    dataframe_conversion_issues = pd.DataFrame(conversion_issues)

    return dataframe, dataframe_conversion_issues


def build_conversion_summary(
    dataframe_conversion_issues: pd.DataFrame
) -> pd.DataFrame:
    """
    Crée un résumé du nombre d'échecs de conversion pour chaque colonne convertie.

    Les colonnes sans erreur sont aussi présentes dans le tableau, avec 0 échec.
    """
    expected_columns = pd.DataFrame(
        {
            "colonne": NUMERIC_COLUMNS + DATE_COLUMNS
        }
    )

    if dataframe_conversion_issues.empty:
        summary = expected_columns.copy()
        summary["echecs_conversion"] = 0
        return summary

    counts = (
        dataframe_conversion_issues["colonne"]
        .value_counts()
        .rename_axis("colonne")
        .reset_index(name="echecs_conversion")
    )

    summary = (
        expected_columns
        .merge(counts, on="colonne", how="left")
        .fillna({"echecs_conversion": 0})
    )

    summary["echecs_conversion"] = (
        summary["echecs_conversion"].astype(int)
    )

    return summary


def detect_semantic_anomalies(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Cherche des anomalies qui restent possibles après une conversion réussie.

    Exemples :
    - durée négative ;
    - latitude hors de [-90, 90] ;
    - longitude hors de [-180, 180] ;
    - publication antérieure à l'observation.

    Ces cas sont différents des échecs de conversion : ils possèdent le bon type
    mais leur sens est incohérent ou suspect.
    """
    anomalies = []

    for index, row in dataframe.iterrows():
        duration = row["duration_seconds"]
        latitude = row["latitude"]
        longitude = row["longitude"]
        observation_date = row["datetime"]
        posted_date = row["date_posted"]

        # Une durée négative n'a pas de sens.
        if pd.notna(duration) and duration < 0:
            anomalies.append(
                {
                    "index_dataframe": index,
                    "type_anomalie": "duree_negative",
                    "valeur": duration,
                }
            )

        # Une latitude doit rester entre -90° et 90°.
        if pd.notna(latitude) and not -90 <= latitude <= 90:
            anomalies.append(
                {
                    "index_dataframe": index,
                    "type_anomalie": "latitude_hors_plage",
                    "valeur": latitude,
                }
            )

        # Une longitude doit rester entre -180° et 180°.
        if pd.notna(longitude) and not -180 <= longitude <= 180:
            anomalies.append(
                {
                    "index_dataframe": index,
                    "type_anomalie": "longitude_hors_plage",
                    "valeur": longitude,
                }
            )

        # Une publication avant l'observation est chronologiquement suspecte.
        if (
            pd.notna(observation_date)
            and pd.notna(posted_date)
            and posted_date < observation_date
        ):
            anomalies.append(
                {
                    "index_dataframe": index,
                    "type_anomalie": "publication_avant_observation",
                    "valeur": (
                        f"observation={observation_date}; "
                        f"publication={posted_date}"
                    ),
                }
            )

    return pd.DataFrame(anomalies)


# ============================================================================
# 4. CRÉATION DE LA CIBLE ARTIFICIELLE — PHASE 3
# ============================================================================

def create_target(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Crée la variable binaire is_hoax.

    Règle :
    Un relevé est étiqueté comme canular si le commentaire contient au moins
    un mot-clé explicitement associé à une fraude, une plaisanterie ou une
    mise en scène.

    Attention :
    Cette cible est une pseudo-étiquette, et non une vérité terrain. Elle dépend
    directement de la liste de mots-clés et peut générer des faux positifs et
    des faux négatifs.
    """
    dataframe = dataframe.copy()

    # re.escape protège chaque mot-clé afin qu'il soit interprété littéralement.
    pattern_hoax = "|".join(
        re.escape(keyword)
        for keyword in HOAX_KEYWORDS
    )

    # Préparation du texte des commentaires.
    dataframe["comments_clean"] = (
        dataframe["comments"]
        .fillna("")
        .astype(str)
        .str.lower()
    )

    # La cible est 1 si au moins un mot-clé est présent, sinon 0.
    dataframe["is_hoax"] = (
        dataframe["comments_clean"]
        .str.contains(
            pattern_hoax,
            regex=True,
            na=False,
        )
        .astype(int)
    )

    # Cette fonction identifie les mots exacts qui ont déclenché la règle.
    # Elle est utile pour vérifier manuellement les exemples de canulars.
    def find_trigger_words(comment: str) -> str:
        text = str(comment).lower()

        words_found = [
            keyword
            for keyword in HOAX_KEYWORDS
            if keyword in text
        ]

        return ", ".join(words_found)

    dataframe["mots_declencheurs"] = dataframe["comments"].apply(
        find_trigger_words
    )

    return dataframe


# ============================================================================
# 5. CRÉATION DES VARIABLES POUR LES MODÈLES
# ============================================================================

def add_feature_engineering(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Ajoute des variables dérivées des dates et prépare les textes du modèle.

    Deux textes combinés sont produits :
    - text_features_with_leakage : contient comments et sert uniquement au
      premier modèle, volontairement fuité ;
    - text_features_without_leakage : ne contient pas comments et sert au modèle
      plus réaliste de la phase 5.
    """
    dataframe = dataframe.copy()

    # Le modèle ne peut pas traiter directement des objets datetime.
    # On en extrait des composantes numériques.
    dataframe["observation_year"] = dataframe["datetime"].dt.year
    dataframe["observation_month"] = dataframe["datetime"].dt.month
    dataframe["observation_hour"] = dataframe["datetime"].dt.hour

    # Cette colonne est produite uniquement pour le modèle initial.
    # Elle sera retirée du modèle sans fuite, car date_posted est renseignée
    # après le dépôt du signalement.
    dataframe["posted_year"] = dataframe["date_posted"].dt.year

    # Texte utilisé par le modèle initial.
    # Il contient comments, donc une fuite existe puisque is_hoax est construite
    # à partir de mots présents dans comments.
    dataframe["text_features_with_leakage"] = (
        "comment " + dataframe["comments"].fillna("").astype(str)
        + " city " + dataframe["city"].fillna("").astype(str)
        + " state " + dataframe["state"].fillna("").astype(str)
        + " country " + dataframe["country"].fillna("").astype(str)
        + " shape " + dataframe["shape"].fillna("").astype(str)
    )

    # Texte utilisé par le modèle sans fuite.
    # Le commentaire n'est pas présent : le modèle ne peut pas retrouver
    # directement les mots utilisés dans la règle de création de la cible.
    dataframe["text_features_without_leakage"] = (
        "city " + dataframe["city"].fillna("").astype(str)
        + " state " + dataframe["state"].fillna("").astype(str)
        + " country " + dataframe["country"].fillna("").astype(str)
        + " shape " + dataframe["shape"].fillna("").astype(str)
    )

    return dataframe


def build_model(
    text_column: str,
    numeric_columns: list,
    max_features: int,
) -> Pipeline:
    """
    Construit un pipeline de machine learning complet.

    Le pipeline comprend :
    - TfidfVectorizer pour convertir le texte en variables numériques ;
    - SimpleImputer pour remplacer les valeurs numériques absentes par la
      médiane de leur colonne ;
    - LogisticRegression pour prédire is_hoax.

    Parameters
    ----------
    text_column : str
        Nom de la colonne textuelle à vectoriser.
    numeric_columns : list
        Noms des colonnes numériques.
    max_features : int
        Nombre maximal de mots ou expressions conservés par TF-IDF.
    """
    preprocessing = ColumnTransformer(
        transformers=[
            (
                "texte",
                TfidfVectorizer(
                    lowercase=True,
                    min_df=2,
                    max_features=max_features,
                    ngram_range=(1, 2),
                ),
                text_column,
            ),
            (
                "numerique",
                Pipeline(
                    steps=[
                        # Les valeurs absentes sont remplacées par la médiane.
                        ("imputer", SimpleImputer(strategy="median")),
                    ]
                ),
                numeric_columns,
            ),
        ]
    )

    model = Pipeline(
        steps=[
            ("preprocessing", preprocessing),
            (
                "classifier",
                LogisticRegression(
                    # Certaines données textuelles demandent plus d'itérations
                    # pour que l'optimisation converge.
                    max_iter=1000,

                    # Compense le déséquilibre entre canulars et non-canulars.
                    class_weight="balanced",

                    # Rend l'entraînement reproductible.
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )

    return model


def calculate_metrics(y_true: pd.Series, y_pred) -> dict:
    """
    Calcule les métriques principales sur la classe positive « canular ».

    - precision : parmi les relevés prédits canulars, part réellement étiquetée
      canular selon la règle de la phase 3 ;
    - recall : parmi tous les canulars réellement présents, part détectée ;
    - accuracy : part de prédictions correctes sur l'ensemble des relevés.

    zero_division=0 évite une erreur si un modèle ne prédit aucun canular.
    """
    return {
        "precision": precision_score(
            y_true,
            y_pred,
            zero_division=0,
        ),
        "recall": recall_score(
            y_true,
            y_pred,
            zero_division=0,
        ),
        "accuracy": accuracy_score(
            y_true,
            y_pred,
        ),
    }


def build_confusion_dataframe(y_true: pd.Series, y_pred) -> pd.DataFrame:
    """
    Construit une matrice de confusion lisible et exportable en CSV.
    """
    matrix = confusion_matrix(y_true, y_pred)

    return pd.DataFrame(
        matrix,
        index=[
            "Reel_non_canular",
            "Reel_canular",
        ],
        columns=[
            "Predit_non_canular",
            "Predit_canular",
        ],
    )


# ============================================================================
# 6. FONCTION PRINCIPALE — EXÉCUTION DE TOUTES LES PHASES
# ============================================================================

def main() -> None:
    """
    Exécute l'ensemble du pipeline, depuis le téléchargement jusqu'aux exports.

    Tous les fichiers produits par le script sont regroupés dans :
    outputs/resultats_analyse/
    """
    # Le dossier du projet est le dossier contenant analyse.py.
    project_dir = Path(__file__).resolve().parent

    # Dossier contenant le CSV téléchargé.
    data_dir = project_dir / "data"

    # Dossier général réservé aux résultats.
    outputs_dir = project_dir / "outputs"

    # Sous-dossier dédié uniquement aux sorties de analyse.py.
    result_dir = outputs_dir / "resultats_analyse"

    # Création des dossiers s'ils n'existent pas.
    data_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    # Emplacement local du fichier téléchargé.
    data_path = data_dir / "releves_klaxo3.csv"

    # ------------------------------------------------------------------------
    # PHASE 1 — Télécharger et charger le fichier
    # ------------------------------------------------------------------------
    download_data(data_path)

    dataframe, bad_rows, total_rows = load_data_robustly(data_path)

    # Les lignes de structure incorrecte sont sauvegardées à part.
    bad_rows.to_csv(
        result_dir / "lignes_problemes_chargement.csv",
        index=False,
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print("PHASE 1 — OUVRIR LA CAISSE")
    print("=" * 70)
    print(f"Nombre de lignes physiques dans le fichier : {total_rows}")
    print(f"Nombre de lignes chargées : {len(dataframe)}")
    print(f"Nombre de lignes isolées : {len(bad_rows)}")
    print(
        "Vérification : "
        f"{len(dataframe)} + {len(bad_rows)} = "
        f"{len(dataframe) + len(bad_rows)}"
    )

    # ------------------------------------------------------------------------
    # PHASE 2 — Convertir les types et exporter les anomalies
    # ------------------------------------------------------------------------
    dataframe, conversion_issues = convert_types(dataframe)

    conversion_summary = build_conversion_summary(conversion_issues)

    semantic_anomalies = detect_semantic_anomalies(dataframe)

    # Export du détail et du résumé des conversions.
    conversion_issues.to_csv(
        result_dir / "anomalies_conversion.csv",
        index=False,
        encoding="utf-8",
    )

    conversion_summary.to_csv(
        result_dir / "resume_conversions.csv",
        index=False,
        encoding="utf-8",
    )

    semantic_anomalies.to_csv(
        result_dir / "anomalies_metier.csv",
        index=False,
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print("PHASE 2 — TYPAGE ET ANOMALIES")
    print("=" * 70)
    print("Nombre d'échecs de conversion par colonne :")
    print(conversion_summary.to_string(index=False))

    if semantic_anomalies.empty:
        print("\nAucune anomalie sémantique détectée.")
    else:
        print("\nNombre d'anomalies sémantiques par type :")
        print(
            semantic_anomalies["type_anomalie"]
            .value_counts()
            .to_string()
        )

    # ------------------------------------------------------------------------
    # PHASE 3 — Créer la cible artificielle is_hoax
    # ------------------------------------------------------------------------
    dataframe = create_target(dataframe)

    total_observations = len(dataframe)
    hoax_count = int(dataframe["is_hoax"].sum())
    hoax_ratio = dataframe["is_hoax"].mean()

    # Export de toutes les lignes marquées comme canulars.
    dataframe.loc[
        dataframe["is_hoax"] == 1,
        [
            "datetime",
            "city",
            "state",
            "country",
            "shape",
            "duration_seconds",
            "comments",
            "mots_declencheurs",
            "is_hoax",
        ],
    ].to_csv(
        result_dir / "releves_etiquetes_canulars.csv",
        index=False,
        encoding="utf-8",
    )

    # Calcul du nombre d'occurrences de chaque mot-clé.
    keyword_counts = pd.DataFrame(
        [
            {
                "mot_cle": keyword,
                "nombre_commentaires": int(
                    dataframe["comments_clean"]
                    .str.contains(
                        re.escape(keyword),
                        regex=True,
                        na=False,
                    )
                    .sum()
                ),
            }
            for keyword in HOAX_KEYWORDS
        ]
    ).sort_values(
        "nombre_commentaires",
        ascending=False,
    )

    keyword_counts.to_csv(
        result_dir / "compte_mots_cles_canular.csv",
        index=False,
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print("PHASE 3 — CRÉATION DE LA CIBLE")
    print("=" * 70)
    print(f"Nombre total de relevés : {total_observations}")
    print(f"Nombre de relevés étiquetés canulars : {hoax_count}")
    print(f"Proportion de canulars : {hoax_ratio:.2%}")

    # ------------------------------------------------------------------------
    # Préparation des variables communes aux phases 4, 5 et 6
    # ------------------------------------------------------------------------
    dataframe = add_feature_engineering(dataframe)

    # y est la cible binaire créée en phase 3.
    y = dataframe["is_hoax"]

    # Les indices sont séparés une seule fois, puis réutilisés pour tous les
    # modèles. Cela garantit que les comparaisons sont faites sur le même jeu
    # de test.
    train_indices, test_indices = train_test_split(
        dataframe.index,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    # ------------------------------------------------------------------------
    # PHASE 4 — Premier modèle, volontairement avec fuite de données
    # ------------------------------------------------------------------------
    # Le premier modèle utilise comments, où la cible a été construite.
    # Il sert à montrer pourquoi ses résultats ne sont pas réalistes.
    numeric_columns_with_leakage = [
        "duration_seconds",
        "latitude",
        "longitude",
        "observation_year",
        "observation_month",
        "observation_hour",
        "posted_year",
    ]

    features_with_leakage = (
        ["text_features_with_leakage"]
        + numeric_columns_with_leakage
    )

    x_with_leakage = dataframe[features_with_leakage].copy()

    model_with_leakage = build_model(
        text_column="text_features_with_leakage",
        numeric_columns=numeric_columns_with_leakage,
        max_features=30_000,
    )

    # Entraînement uniquement sur le jeu d'entraînement.
    model_with_leakage.fit(
        x_with_leakage.loc[train_indices],
        y.loc[train_indices],
    )

    # Évaluation uniquement sur le jeu de test jamais vu.
    predictions_with_leakage = model_with_leakage.predict(
        x_with_leakage.loc[test_indices]
    )

    metrics_with_leakage = calculate_metrics(
        y.loc[test_indices],
        predictions_with_leakage,
    )

    confusion_with_leakage = build_confusion_dataframe(
        y.loc[test_indices],
        predictions_with_leakage,
    )

    print("\n" + "=" * 70)
    print("PHASE 4 — PREMIER MODÈLE AVEC FUITE")
    print("=" * 70)
    print(
        f"Precision : {metrics_with_leakage['precision']:.2%}"
    )
    print(
        f"Recall : {metrics_with_leakage['recall']:.2%}"
    )
    print(
        f"Accuracy : {metrics_with_leakage['accuracy']:.2%}"
    )

    # ------------------------------------------------------------------------
    # PHASE 5 — Audit et modèle sans fuite de données
    # ------------------------------------------------------------------------
    # Ce tableau sera également utile à recopier/adopter dans RAPPORT.md.
    audit_variables = pd.DataFrame(
        [
            {
                "colonne": "comments",
                "qui_renseigne": "Témoin",
                "moment": "Lors de la déclaration",
                "connait_deja_la_cible": (
                    "Oui : la cible est construite à partir de ce texte"
                ),
                "decision": "Supprimée",
            },
            {
                "colonne": "city",
                "qui_renseigne": "Témoin",
                "moment": "Lors de la déclaration",
                "connait_deja_la_cible": "Non",
                "decision": "Conservée",
            },
            {
                "colonne": "state",
                "qui_renseigne": "Témoin ou système de géocodage",
                "moment": "Déclaration ou juste après",
                "connait_deja_la_cible": "Non directement",
                "decision": "Conservée",
            },
            {
                "colonne": "country",
                "qui_renseigne": "Témoin ou système de géocodage",
                "moment": "Déclaration ou juste après",
                "connait_deja_la_cible": "Non directement",
                "decision": "Conservée",
            },
            {
                "colonne": "shape",
                "qui_renseigne": "Témoin",
                "moment": "Lors de la déclaration",
                "connait_deja_la_cible": "Non",
                "decision": "Conservée",
            },
            {
                "colonne": "duration_seconds",
                "qui_renseigne": "Témoin ou système de traitement",
                "moment": "Déclaration ou juste après",
                "connait_deja_la_cible": "Non directement",
                "decision": "Conservée",
            },
            {
                "colonne": "latitude",
                "qui_renseigne": "Capteur ou système de géocodage",
                "moment": "À la réception si le capteur la fournit",
                "connait_deja_la_cible": "Non directement",
                "decision": "Conservée",
            },
            {
                "colonne": "longitude",
                "qui_renseigne": "Capteur ou système de géocodage",
                "moment": "À la réception si le capteur la fournit",
                "connait_deja_la_cible": "Non directement",
                "decision": "Conservée",
            },
            {
                "colonne": "datetime",
                "qui_renseigne": "Témoin",
                "moment": "Lors de la déclaration",
                "connait_deja_la_cible": "Non",
                "decision": "Conservée sous forme année, mois et heure",
            },
            {
                "colonne": "date_posted",
                "qui_renseigne": "Service de traitement",
                "moment": "Après la réception et le traitement",
                "connait_deja_la_cible": (
                    "Non disponible au moment de la prédiction"
                ),
                "decision": "Supprimée",
            },
        ]
    )

    audit_variables.to_csv(
        result_dir / "audit_variables_phase5.csv",
        index=False,
        encoding="utf-8",
    )

    # Le modèle sans fuite n'utilise ni comments, ni commentaires nettoyés,
    # ni mots déclencheurs, ni date_posted / posted_year.
    numeric_columns_without_leakage = [
        "duration_seconds",
        "latitude",
        "longitude",
        "observation_year",
        "observation_month",
        "observation_hour",
    ]

    features_without_leakage = (
        ["text_features_without_leakage"]
        + numeric_columns_without_leakage
    )

    x_without_leakage = dataframe[features_without_leakage].copy()

    model_without_leakage = build_model(
        text_column="text_features_without_leakage",
        numeric_columns=numeric_columns_without_leakage,
        max_features=10_000,
    )

    model_without_leakage.fit(
        x_without_leakage.loc[train_indices],
        y.loc[train_indices],
    )

    predictions_without_leakage = model_without_leakage.predict(
        x_without_leakage.loc[test_indices]
    )

    metrics_without_leakage = calculate_metrics(
        y.loc[test_indices],
        predictions_without_leakage,
    )

    confusion_without_leakage = build_confusion_dataframe(
        y.loc[test_indices],
        predictions_without_leakage,
    )

    # Tableau demandé pour comparer les résultats avant/après suppression
    # des fuites de données.
    comparison_phase5 = pd.DataFrame(
        [
            {
                "version_modele": "Avec fuite",
                **metrics_with_leakage,
            },
            {
                "version_modele": "Sans fuite",
                **metrics_without_leakage,
            },
        ]
    )

    print("\n" + "=" * 70)
    print("PHASE 5 — MODÈLE SANS FUITE")
    print("=" * 70)
    print(comparison_phase5.to_string(index=False))

    # ------------------------------------------------------------------------
    # PHASE 6 — Baseline du stagiaire
    # ------------------------------------------------------------------------
    # Le DummyClassifier prédit systématiquement la classe 0 :
    # « pas canular », indépendamment des informations de X.
    intern_baseline = DummyClassifier(
        strategy="constant",
        constant=0,
    )

    intern_baseline.fit(
        x_without_leakage.loc[train_indices],
        y.loc[train_indices],
    )

    predictions_intern = intern_baseline.predict(
        x_without_leakage.loc[test_indices]
    )

    metrics_intern = calculate_metrics(
        y.loc[test_indices],
        predictions_intern,
    )

    confusion_intern = build_confusion_dataframe(
        y.loc[test_indices],
        predictions_intern,
    )

    # Tableau final : modèle réel sans fuite contre modèle naïf.
    comparison_phase6 = pd.DataFrame(
        [
            {
                "modele": "Modèle sans fuite",
                **metrics_without_leakage,
            },
            {
                "modele": "Stagiaire : toujours non-canular",
                **metrics_intern,
            },
        ]
    )

    print("\n" + "=" * 70)
    print("PHASE 6 — COMPARAISON AVEC LE STAGIAIRE")
    print("=" * 70)
    print(comparison_phase6.to_string(index=False))

    # ------------------------------------------------------------------------
    # EXPORTS FINAUX
    # ------------------------------------------------------------------------
    # Tous ces fichiers seront déposés dans outputs/resultats_analyse/.
    comparison_phase5.to_csv(
        result_dir / "resultats_phase5_avant_apres_fuite.csv",
        index=False,
        encoding="utf-8",
    )

    comparison_phase6.to_csv(
        result_dir / "resultats_phase6_comparaison_stagiaire.csv",
        index=False,
        encoding="utf-8",
    )

    confusion_with_leakage.to_csv(
        result_dir / "matrice_confusion_modele_avec_fuite.csv",
        index=True,
        encoding="utf-8",
    )

    confusion_without_leakage.to_csv(
        result_dir / "matrice_confusion_modele_sans_fuite.csv",
        index=True,
        encoding="utf-8",
    )

    confusion_intern.to_csv(
        result_dir / "matrice_confusion_modele_stagiaire.csv",
        index=True,
        encoding="utf-8",
    )

    # Export d'un tableau général pratique pour retrouver les principaux
    # nombres du rapport dans un seul fichier.
    summary_final = pd.DataFrame(
        [
            {
                "indicateur": "lignes_physiques",
                "valeur": total_rows,
            },
            {
                "indicateur": "lignes_chargees",
                "valeur": len(dataframe),
            },
            {
                "indicateur": "lignes_isolees",
                "valeur": len(bad_rows),
            },
            {
                "indicateur": "nombre_canulars",
                "valeur": hoax_count,
            },
            {
                "indicateur": "proportion_canulars",
                "valeur": hoax_ratio,
            },
            {
                "indicateur": "precision_avec_fuite",
                "valeur": metrics_with_leakage["precision"],
            },
            {
                "indicateur": "recall_avec_fuite",
                "valeur": metrics_with_leakage["recall"],
            },
            {
                "indicateur": "accuracy_avec_fuite",
                "valeur": metrics_with_leakage["accuracy"],
            },
            {
                "indicateur": "precision_sans_fuite",
                "valeur": metrics_without_leakage["precision"],
            },
            {
                "indicateur": "recall_sans_fuite",
                "valeur": metrics_without_leakage["recall"],
            },
            {
                "indicateur": "accuracy_sans_fuite",
                "valeur": metrics_without_leakage["accuracy"],
            },
            {
                "indicateur": "accuracy_stagiaire",
                "valeur": metrics_intern["accuracy"],
            },
            {
                "indicateur": "precision_stagiaire",
                "valeur": metrics_intern["precision"],
            },
            {
                "indicateur": "recall_stagiaire",
                "valeur": metrics_intern["recall"],
            },
        ]
    )

    summary_final.to_csv(
        result_dir / "resume_final.csv",
        index=False,
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print("ANALYSE TERMINÉE")
    print("=" * 70)
    print("Tous les fichiers générés par analyse.py sont disponibles dans :")
    print(result_dir)


# Le script n'exécute main() que lorsqu'il est lancé directement avec :
# python analyse.py
if __name__ == "__main__":
    main()