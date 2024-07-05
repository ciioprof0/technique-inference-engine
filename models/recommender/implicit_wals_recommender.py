import numpy as np
import tensorflow as tf
from .recommender import Recommender
from implicit.als import AlternatingLeastSquares
from sklearn.metrics import mean_squared_error
from scipy import sparse
import copy
from constants import PredictionMethod
from utils import calculate_predicted_matrix


class ImplicitWalsRecommender(Recommender):
    """A WALS matrix factorization collaborative filtering recommender model."""

    # Abstraction function:
    # AF(model, m, n, k, num_new_users) = a matrix factorization collaborative filtering recommendation model
    #   of embedding dimension k with m entity embeddings model.user_factors
    #   and n item embeddings model.item_factors.
    #   The model has performed cold start prediction for num_new_users.
    # Rep invariant:
    #   - m > 0
    #   - n > 0
    #   - k > 0
    # Safety from rep exposure:
    #   - k is private and immutable
    #   - model is never returned

    def __init__(self, m: int, n: int, k: int = 10):
        """Initializes a new ImplicitWALSRecommender object.

        Args:
            m: number of entities.  Requires m > 0.
            n: number of items.  Requires n > 0.
            k: embedding dimension.  Requires k > 0.
        """
        assert m > 0
        assert n > 0
        assert k > 0

        self._m = m
        self._n = n
        self._k = k
        self._model = None

        # for tracking how many new users we've seen so far
        self._num_new_users = 0

        self._checkrep()

    def _checkrep(self):
        """Asserts the rep invariant."""
        #   - m > 0
        assert self._m > 0
        #   - n > 0
        assert self._n > 0
        #   - k > 0
        assert self._k > 0

    @property
    def U(self) -> np.ndarray:
        """Gets U as a factor of the factorization UV^T.  Requires model to be trained."""
        assert self._model

        self._checkrep()
        return np.copy(self._model.user_factors)

    @property
    def V(self) -> np.ndarray:
        """Gets V as a factor of the factorization UV^T.  Requires model to be trained."""
        assert self._model

        self._checkrep()
        return np.copy(self._model.item_factors)

    def fit(
        self,
        data: tf.SparseTensor,
        num_iterations: int = 20,
        c: float = 0.024,
        regularization_coefficient: float = 0.01,
    ):
        """Fits the model to data.

        Args:
            data: an mxn tensor of training data.
            num_iterations: number of training iterations to execute.
            c: weight for negative training examples.  Requires 0 < c < 1.
            regularization_coefficient: coefficient on the embedding regularization term.

        Mutates:
            The recommender to the new trained state.
        """
        assert 0 < c < 1

        alpha = (1 / c) - 1
        self._model = AlternatingLeastSquares(
            factors=self._k,
            regularization=regularization_coefficient,
            iterations=num_iterations,
            alpha=alpha,
        )

        row_indices = tuple(index[0] for index in data.indices)
        column_indices = tuple(index[1] for index in data.indices)
        sparse_data = sparse.csr_matrix(
            (data.values, (row_indices, column_indices)), shape=data.shape
        )

        self._model.fit(sparse_data)

        self._checkrep()

    def evaluate(self, test_data: tf.SparseTensor, method: PredictionMethod=PredictionMethod.DOT) -> float:
        predictions_matrix = self.predict(method)

        row_indices = tuple(index[0] for index in test_data.indices)
        column_indices = tuple(index[1] for index in test_data.indices)
        prediction_values = predictions_matrix[row_indices, column_indices]

        self._checkrep()
        return mean_squared_error(test_data.values, prediction_values)

    def predict(self, method: PredictionMethod=PredictionMethod.DOT) -> np.ndarray:
        self._checkrep()

        return calculate_predicted_matrix(self._model.user_factors, self._model.item_factors, method)

    def predict_new_entity(self, entity: tf.SparseTensor, method: PredictionMethod=PredictionMethod.DOT) -> np.array:
        # just need an item 0 for all entity indices
        row_indices = np.zeros(len(entity.indices))
        column_indices = entity.indices[:, 0]

        sparse_data = sparse.csr_matrix(
            (entity.values, (row_indices, column_indices)), shape=(1, entity.shape[0])
        )

        user_id = self._m + self._num_new_users

        self._model.partial_fit_users((user_id,), sparse_data)

        self._num_new_users += 1

        self._checkrep()
    
        return np.squeeze(calculate_predicted_matrix(self._model.user_factors[user_id], self._model.item_factors, method))
