"""Custom transformer required when loading the fitted preprocessing pipeline."""

import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.preprocessing import MultiLabelBinarizer


class MultiLabelEncoder(BaseEstimator, TransformerMixin):
    """Encode semicolon-separated values in the foundation-type column."""

    def __init__(self, column="FNDTYPE", delimiter=";"):
        self.column = column
        self.delimiter = delimiter
        self.mlb = None

    def fit(self, features, target=None):
        features_copy = features.copy()
        list_column = f"{self.column}_list"
        features_copy[list_column] = features_copy[self.column].str.split(
            self.delimiter
        )
        self.mlb = MultiLabelBinarizer()
        self.mlb.fit(features_copy[list_column])
        return self

    def transform(self, features):
        features_copy = features.copy()
        list_column = f"{self.column}_list"
        features_copy[list_column] = features_copy[self.column].str.split(
            self.delimiter
        )
        encoded = self.mlb.transform(features_copy[list_column])
        encoded_frame = pd.DataFrame(
            encoded,
            columns=[
                f"{self.column}_{label}" for label in self.mlb.classes_
            ],
            index=features.index,
        )
        features_copy = features_copy.drop(
            [self.column, list_column], axis=1
        )
        return pd.concat([features_copy, encoded_frame], axis=1)