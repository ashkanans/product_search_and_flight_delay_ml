import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from pyspark.ml import Pipeline
from pyspark.ml.classification import LogisticRegression, RandomForestClassifier
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
from pyspark.ml.feature import StringIndexer, OneHotEncoder, VectorAssembler
from pyspark.ml.tuning import CrossValidator
from pyspark.ml.tuning import ParamGridBuilder
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.functions import col, isnan, when, count


class FlightDataAnalyzer:
    def __init__(self, df: DataFrame):
        self.df = df

    def check_missing_values(self):
        """Check for null or missing values and display their count."""
        missing_counts = self.df.select(
            [
                count(when(isnan(c) | col(c).isNull(), c)).alias(c)
                if dict(self.df.dtypes)[c] in ["double", "float"]
                else count(when(col(c).isNull(), c)).alias(c)
                for c in self.df.columns
            ]
        )
        missing_counts.show()

    def plot_roc_curve(self, model, test_df):
        """Plot the ROC curve for the given model on the test set."""
        # Generate predictions and extract probabilities for ROC curve
        predictions = model.transform(test_df)
        results = predictions.select("label", "probability").toPandas()
        results["probability"] = results["probability"].apply(lambda x: x[1])

        # Calculate ROC curve
        from sklearn.metrics import roc_curve
        fpr, tpr, _ = roc_curve(results["label"], results["probability"])

        # Plot ROC curve
        plt.figure(figsize=(8, 6))
        plt.plot(fpr, tpr, color="blue", label="ROC Curve")
        plt.plot([0, 1], [0, 1], color="red", linestyle="--")
        plt.xlabel("False Positive Rate")
        plt.ylabel("True Positive Rate")
        plt.title("ROC Curve")
        plt.legend()
        plt.show()

    def plot_feature_importances(self, model):
        """Plot feature importances for the Random Forest model."""
        importances = model.featureImportances.toArray()
        feature_names = model.featureNames
        indices = np.argsort(importances)[::-1]

        plt.figure(figsize=(10, 6))
        plt.bar(range(len(importances)), importances[indices], align="center")
        plt.xticks(range(len(importances)), [feature_names[i] for i in indices], rotation=90)
        plt.xlabel("Feature")
        plt.ylabel("Importance")
        plt.title("Feature Importances (Random Forest)")
        plt.tight_layout()
        plt.show()

    def plot_data_distributions(self):
        """Visualize distributions of delay data and relevant columns."""
        # Convert necessary columns to Pandas for visualization
        dep_delay_df = self.df.select("DEP_DELAY").dropna().toPandas()
        arr_delay_df = self.df.select("ARR_DELAY").dropna().toPandas()

        # Plot distributions
        plt.figure(figsize=(12, 6))
        sns.histplot(dep_delay_df["DEP_DELAY"], kde=True, bins=30, color="skyblue").set_title(
            "Departure Delay Distribution")
        plt.xlabel("Minutes")
        plt.show()

        plt.figure(figsize=(12, 6))
        sns.histplot(arr_delay_df["ARR_DELAY"], kde=True, bins=30, color="salmon").set_title(
            "Arrival Delay Distribution")
        plt.xlabel("Minutes")
        plt.show()

    def prepare_binary_label(self):
        """Add a binary label column for flights delayed by more than 15 minutes at departure."""
        self.df = self.df.withColumn("label", F.when(F.col("DEP_DELAY") > 15.0, 1).otherwise(0))
        print("Added binary label column for departure delay classification.")
        return self.df

    def tune_logistic_regression(self, train_df):
        """Tune Logistic Regression model with hyperparameter grid."""
        lr = LogisticRegression(featuresCol="features", labelCol="label")

        # Define the hyperparameter grid
        paramGrid = (ParamGridBuilder()
                     .addGrid(lr.regParam, [0.01, 0.1, 0.5])
                     .addGrid(lr.elasticNetParam, [0.0, 0.5, 1.0])  # 0.0=L2, 1.0=L1, 0.5=Elastic Net
                     .build())

        print("Logistic Regression hyperparameter grid defined.")
        return lr, paramGrid

    def cross_validate_model(self, model, paramGrid, train_df):
        """Perform cross-validation with BinaryClassificationEvaluator and return the best model."""
        evaluator = BinaryClassificationEvaluator(labelCol="label", metricName="areaUnderROC")

        # Set up cross-validator
        crossval = CrossValidator(
            estimator=model,
            estimatorParamMaps=paramGrid,
            evaluator=evaluator,
            numFolds=5
        )

        # Perform cross-validation and get the best model
        cv_model = crossval.fit(train_df)
        print("Cross-validation completed. Best model selected based on AUC.")

        return cv_model.bestModel

    def tune_random_forest(self, train_df):
        """Tune Random Forest model with hyperparameter grid."""
        rf = RandomForestClassifier(featuresCol="features", labelCol="label")

        # Define the hyperparameter grid
        paramGrid = (ParamGridBuilder()
                     .addGrid(rf.numTrees, [20, 50, 100])
                     .addGrid(rf.maxDepth, [5, 10, 15])
                     .build())

        print("Random Forest hyperparameter grid defined.")
        return rf, paramGrid

    def train_logistic_regression(self, train_df):
        """Train a Logistic Regression model."""
        lr = LogisticRegression(featuresCol="features", labelCol="label")
        lr_model = lr.fit(train_df)
        print("Logistic Regression model trained.")
        return lr_model

    def train_random_forest(self, train_df):
        """Train a Random Forest Classifier model."""
        rf = RandomForestClassifier(featuresCol="features", labelCol="label")
        rf_model = rf.fit(train_df)
        print("Random Forest model trained.")
        return rf_model

    def basic_eda(self):
        """Perform basic EDA including summary statistics and distributions."""
        print("Basic statistics of numerical columns:")
        self.df.describe().show()

        # Plot distributions of delay times
        dep_delay_df = self.df.select("DEP_DELAY").dropna().toPandas()
        arr_delay_df = self.df.select("ARR_DELAY").dropna().toPandas()

        # Plot histogram of departure and arrival delays
        plt.figure(figsize=(10, 5))
        sns.histplot(dep_delay_df["DEP_DELAY"], kde=True, bins=30).set_title("Departure Delay Distribution")
        plt.xlabel("Minutes")
        plt.show(block=True)

        plt.figure(figsize=(10, 5))
        sns.histplot(arr_delay_df["ARR_DELAY"], kde=True, bins=30).set_title("Arrival Delay Distribution")
        plt.xlabel("Minutes")
        plt.show(block=True)

    def predict_with_logistic_regression(self, best_lr_model, test_df):
        """Use the best Logistic Regression model to make predictions on the test set."""
        predictions = best_lr_model.transform(test_df)
        print("Predictions made with Logistic Regression model.")
        return predictions

    def predict_with_random_forest(self, best_rf_model, test_df):
        """Use the best Random Forest model to make predictions on the test set."""
        predictions = best_rf_model.transform(test_df)
        print("Predictions made with Random Forest model.")
        return predictions

    def evaluate_model(self, predictions):
        """Evaluate the model's performance on the test set and print key metrics."""
        # Binary Classification Evaluator for AUC
        binary_evaluator = BinaryClassificationEvaluator(labelCol="label", metricName="areaUnderROC")
        auc = binary_evaluator.evaluate(predictions)

        # Multiclass Classification Evaluator for accuracy, precision, recall, and F1-score
        evaluator = MulticlassClassificationEvaluator(labelCol="label", predictionCol="prediction")
        accuracy = evaluator.evaluate(predictions, {evaluator.metricName: "accuracy"})
        precision = evaluator.evaluate(predictions, {evaluator.metricName: "weightedPrecision"})
        recall = evaluator.evaluate(predictions, {evaluator.metricName: "weightedRecall"})
        f1 = evaluator.evaluate(predictions, {evaluator.metricName: "f1"})

        print(f"Model Evaluation Metrics:")
        print(f"AUC: {auc}")
        print(f"Accuracy: {accuracy}")
        print(f"Precision: {precision}")
        print(f"Recall: {recall}")
        print(f"F1-score: {f1}")

        # Confusion Matrix
        confusion_matrix = predictions.groupBy("label", "prediction").count().orderBy("label", "prediction")
        print("Confusion Matrix:")
        confusion_matrix.show()

    def handle_missing_values(self):
        """Handle missing values by imputing or dropping based on analysis of column importance and data structure."""

        # 1. Impute missing values in DEP_DELAY and ARR_DELAY with 0.0.
        # Missing values for these columns are treated as no delay.
        self.df = self.df.withColumn("DEP_DELAY", F.coalesce(F.col("DEP_DELAY"), F.lit(0.0)))
        self.df = self.df.withColumn("ARR_DELAY", F.coalesce(F.col("ARR_DELAY"), F.lit(0.0)))
        print("Imputed missing values in DEP_DELAY and ARR_DELAY with 0.0.")

        # 2. Drop rows with missing values in other essential columns.
        # These columns are critical for modeling delays, so rows with missing values in these columns should be dropped.
        essential_cols = ["AIRLINE", "ORIGIN", "DEST", "CRS_DEP_TIME", "DISTANCE"]
        self.df = self.df.dropna(subset=essential_cols)
        print("Dropped rows with missing values in essential columns.")

        # 3. Impute missing values in delay-related columns with 0.
        # These columns indicate specific types of delays. If missing, assume no delay of that type occurred.
        delay_cols = ["DELAY_DUE_CARRIER", "DELAY_DUE_WEATHER", "DELAY_DUE_NAS", "DELAY_DUE_SECURITY",
                      "DELAY_DUE_LATE_AIRCRAFT"]
        for col in delay_cols:
            self.df = self.df.withColumn(col, F.coalesce(F.col(col), F.lit(0.0)))
        print("Imputed missing values in delay-related columns with 0.")

        return self.df

    def feature_engineering(self):
        """Select features, convert categorical columns, and assemble features for modeling."""

        # Columns to keep for modeling
        necessary_cols = ["CRS_DEP_TIME", "DISTANCE", "AIRLINE", "ORIGIN", "DEST",
                          "DELAY_DUE_CARRIER", "DELAY_DUE_WEATHER", "DELAY_DUE_NAS",
                          "DELAY_DUE_SECURITY", "DELAY_DUE_LATE_AIRCRAFT"]

        # Filter DataFrame to include only necessary columns
        self.df = self.df.select(*necessary_cols, "DEP_DELAY")

        # Convert categorical columns using StringIndexer and OneHotEncoder
        categorical_cols = ["AIRLINE", "ORIGIN", "DEST"]
        stages = []

        for col_name in categorical_cols:
            # StringIndexer for categorical features
            indexer = StringIndexer(inputCol=col_name, outputCol=f"{col_name}_Index")
            encoder = OneHotEncoder(inputCol=indexer.getOutputCol(), outputCol=f"{col_name}_Vec")
            stages += [indexer, encoder]

        # Assemble features
        feature_cols = ["CRS_DEP_TIME", "DISTANCE", "DELAY_DUE_CARRIER",
                        "DELAY_DUE_WEATHER", "DELAY_DUE_NAS", "DELAY_DUE_SECURITY",
                        "DELAY_DUE_LATE_AIRCRAFT"] + [f"{col}_Vec" for col in categorical_cols]

        assembler = VectorAssembler(inputCols=feature_cols, outputCol="features")
        stages.append(assembler)

        # Create and apply the pipeline
        pipeline = Pipeline(stages=stages)
        pipeline_model = pipeline.fit(self.df)
        self.df = pipeline_model.transform(self.df)

        # Select only necessary columns for modeling
        self.df = self.df.select("features", "DEP_DELAY")
        return self.df

    def split_data(self):
        """Split data into training and testing sets."""
        train, test = self.df.randomSplit([0.8, 0.2], seed=42)
        print("Split data into training and testing sets.")
        # Check the distribution of labels in train and test sets
        train_distribution = train.groupBy("label").count()
        test_distribution = test.groupBy("label").count()

        print("Train Set Label Distribution:")
        train_distribution.show()

        print("Test Set Label Distribution:")
        test_distribution.show()

        return train, test

    def enhanced_comprehensive_eda(self):
        """Enhanced EDA with additional statistical insights and visualizations."""

        # Convert PySpark DataFrame to Pandas DataFrame for detailed visualization
        pandas_df = self.df.toPandas()

        # 1. Basic Descriptive Statistics with Delay Rates
        print("1. Basic Statistics with Delay Rates")
        total_flights = self.df.count()
        delayed_flights = self.df.filter(F.col("DEP_DELAY") > 0).count()
        delay_rate = delayed_flights / total_flights
        print(f"Total Flights: {total_flights}")
        print(f"Delayed Flights: {delayed_flights} ({delay_rate:.2%})")

        # Mean and standard deviation of departure and arrival delays
        print("Average and Standard Deviation of Delays:")
        delay_stats = pandas_df[['DEP_DELAY', 'ARR_DELAY']].describe().loc[['mean', 'std']]
        print(delay_stats)

        # 2. Delay Distribution Visualizations
        print("\n2. Visualizing Delay Distributions")
        plt.figure(figsize=(12, 6))
        sns.histplot(pandas_df["DEP_DELAY"].dropna(), bins=30, kde=True, color="skyblue")
        plt.title("Distribution of Departure Delays")
        plt.xticks(rotation=45, fontsize=8)
        plt.xlabel("Minutes")
        plt.ylabel("Frequency")
        plt.axvline(delay_stats.loc["mean", "DEP_DELAY"], color="red", linestyle="--", label="Mean Delay")
        plt.legend()
        plt.show(block=True)

        plt.figure(figsize=(12, 6))
        sns.histplot(pandas_df["ARR_DELAY"].dropna(), bins=30, kde=True, color="lightgreen")
        plt.title("Distribution of Arrival Delays")
        plt.xticks(rotation=45, fontsize=8)
        plt.xlabel("Minutes")
        plt.ylabel("Frequency")
        plt.axvline(delay_stats.loc["mean", "ARR_DELAY"], color="red", linestyle="--", label="Mean Delay")
        plt.legend()
        plt.show(block=True)

        # 3. Delay Rates by Airline and Cancellation Rates by Airline
        print("\n3. Analyzing Delay and Cancellation Rates by Airline")
        airline_df = self.df.groupBy("AIRLINE").agg(
            F.avg("DEP_DELAY").alias("avg_dep_delay"),
            F.avg("ARR_DELAY").alias("avg_arr_delay"),
            F.count("*").alias("flight_count"),
            F.sum(F.when(F.col("CANCELLED") == 1, 1).otherwise(0)).alias("cancelled_count")
        )
        airline_df = airline_df.withColumn("cancellation_rate", F.col("cancelled_count") / F.col("flight_count"))
        airline_pandas_df = airline_df.toPandas()

        # Bar Plot of Average Delay by Airline
        plt.figure(figsize=(15, 8))
        sns.barplot(data=airline_pandas_df, x="AIRLINE", y="avg_dep_delay", color="coral", label="Departure Delay")
        sns.barplot(data=airline_pandas_df, x="AIRLINE", y="avg_arr_delay", color="skyblue", label="Arrival Delay")
        plt.title("Average Departure and Arrival Delays by Airline")
        plt.ylabel("Average Delay (Minutes)")
        plt.xticks(rotation=45, fontsize=8)
        plt.legend()
        plt.show(block=True)

        # Bar Plot of Cancellation Rate by Airline
        plt.figure(figsize=(15, 8))
        sns.barplot(data=airline_pandas_df, x="AIRLINE", y="cancellation_rate", palette="viridis")
        plt.title("Cancellation Rate by Airline")
        plt.ylabel("Cancellation Rate")
        plt.xticks(rotation=45, fontsize=8)
        plt.show(block=True)

        # 4. Correlation Analysis
        print("\n4. Correlation Heatmap for Numerical Features")
        numerical_columns = ["DEP_DELAY", "ARR_DELAY", "TAXI_OUT", "TAXI_IN", "CRS_ELAPSED_TIME", "ELAPSED_TIME",
                             "AIR_TIME", "DISTANCE", "DELAY_DUE_CARRIER", "DELAY_DUE_WEATHER",
                             "DELAY_DUE_NAS", "DELAY_DUE_SECURITY", "DELAY_DUE_LATE_AIRCRAFT"]
        corr_matrix = pandas_df[numerical_columns].corr()

        plt.figure(figsize=(12, 10))
        sns.heatmap(corr_matrix, annot=True, fmt=".2f", cmap="coolwarm", square=True)
        plt.title("Correlation Heatmap of Numerical Features")
        plt.xticks(rotation=45, fontsize=8)
        plt.yticks(rotation=45, fontsize=8)
        plt.show(block=True)

        # 5. Time-Based Delay Patterns
        print("\n5. Analyzing Delay Patterns by Hour of Day and Day of Week")
        pandas_df['hour_of_day'] = (pandas_df['CRS_DEP_TIME'] // 100).astype(int)
        pandas_df['day_of_week'] = pd.to_datetime(pandas_df['FL_DATE']).dt.dayofweek  # Monday=0, Sunday=6

        # Average Delay by Hour of Day
        hour_delay_stats = pandas_df.groupby("hour_of_day")[["DEP_DELAY", "ARR_DELAY"]].mean()

        plt.figure(figsize=(12, 6))
        hour_delay_stats.plot(kind="bar", stacked=True, color=["coral", "skyblue"])
        plt.title("Average Departure and Arrival Delays by Hour of Day")
        plt.xticks(rotation=45, fontsize=8)
        plt.xlabel("Hour of Day")
        plt.ylabel("Average Delay (Minutes)")
        plt.legend(["Departure Delay", "Arrival Delay"])
        plt.show(block=True)

        # Average Delay by Day of Week
        day_of_week_delay_stats = pandas_df.groupby("day_of_week")[["DEP_DELAY", "ARR_DELAY"]].mean()

        plt.figure(figsize=(12, 6))
        day_of_week_delay_stats.plot(kind="bar", stacked=True, color=["lightgreen", "purple"])
        plt.title("Average Departure and Arrival Delays by Day of the Week")
        plt.xlabel("Day of Week (0=Monday, 6=Sunday)")
        plt.xticks(rotation=45, fontsize=8)
        plt.ylabel("Average Delay (Minutes)")
        plt.legend(["Departure Delay", "Arrival Delay"])
        plt.show(block=True)

        # 6. Cancellation Reasons Analysis
        print("\n6. Cancellation Reasons Analysis")
        cancellation_reason_counts = pandas_df["CANCELLATION_CODE"].value_counts().dropna()
        cancellation_reason_counts.plot(kind="bar", color="salmon")
        plt.title("Distribution of Cancellation Reasons")
        plt.xticks(rotation=45, fontsize=8)
        plt.xlabel("Cancellation Code")
        plt.ylabel("Number of Cancellations")
        plt.show(block=True)

    def comprehensive_eda(self):
        """Perform a comprehensive EDA on the flight delay dataset."""

        # 1. Data Overview
        print("Data Overview:")
        self.df.printSchema()
        self.df.describe().show()

        print("Total rows:", self.df.count())
        print("Null values per column:")
        self.df.select([F.count(F.when(F.col(c).isNull(), c)).alias(c) for c in self.df.columns]).show()

        # 2. Flight Delay Analysis
        print("Distribution of DEP_DELAY and ARR_DELAY:")
        dep_delay_df = self.df.select("DEP_DELAY").dropna().toPandas()
        arr_delay_df = self.df.select("ARR_DELAY").dropna().toPandas()

        plt.figure(figsize=(12, 6))
        sns.histplot(dep_delay_df["DEP_DELAY"], bins=30, kde=True)
        plt.title("Distribution of Departure Delays")
        plt.xlabel("Minutes")
        plt.show()

        plt.figure(figsize=(12, 6))
        sns.histplot(arr_delay_df["ARR_DELAY"], bins=30, kde=True)
        plt.title("Distribution of Arrival Delays")
        plt.xlabel("Minutes")
        plt.show()

        # 3. Analysis by Airline
        print("Average Delays by Airline:")
        self.df.groupBy("AIRLINE").agg(F.avg("DEP_DELAY").alias("avg_dep_delay"),
                                       F.avg("ARR_DELAY").alias("avg_arr_delay")).show()

        print("Flight Counts and Cancellation Rates by Airline:")
        airline_stats = self.df.groupBy("AIRLINE").agg(F.count("*").alias("flight_count"),
                                                       F.sum(F.when(F.col("CANCELLED") == 1, 1).otherwise(0)).alias(
                                                           "cancelled_count"))
        airline_stats = airline_stats.withColumn("cancellation_rate", F.col("cancelled_count") / F.col("flight_count"))
        airline_stats.show()

        # 4. Geographical Analysis
        print("Average Delays by Origin and Destination Airports:")
        origin_delay = self.df.groupBy("ORIGIN").agg(F.avg("DEP_DELAY").alias("avg_dep_delay")).orderBy("avg_dep_delay",
                                                                                                        ascending=False)
        dest_delay = self.df.groupBy("DEST").agg(F.avg("ARR_DELAY").alias("avg_arr_delay")).orderBy("avg_arr_delay",
                                                                                                    ascending=False)
        origin_delay.show()
        dest_delay.show()

        # 5. Time-Based Analysis
        print("Average Delays by Hour of Day:")
        self.df = self.df.withColumn("hour_of_day", (F.col("CRS_DEP_TIME") / 100).cast("int"))
        delay_by_hour = self.df.groupBy("hour_of_day").agg(F.avg("DEP_DELAY").alias("avg_dep_delay"),
                                                           F.avg("ARR_DELAY").alias("avg_arr_delay"))
        delay_by_hour.orderBy("hour_of_day").show()

        # 6. Impact of Different Types of Delays
        print("Impact of Different Delay Types:")
        delay_types = ["DELAY_DUE_CARRIER", "DELAY_DUE_WEATHER", "DELAY_DUE_NAS",
                       "DELAY_DUE_SECURITY", "DELAY_DUE_LATE_AIRCRAFT"]
        delay_impact = self.df.select([F.corr(col, "ARR_DELAY").alias(f"corr_{col}") for col in delay_types])
        delay_impact.show()

        # 7. Cancellation Analysis
        print("Cancellation Reasons Distribution:")
        self.df.groupBy("CANCELLATION_CODE").count().orderBy("count", ascending=False).show()