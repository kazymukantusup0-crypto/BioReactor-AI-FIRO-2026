# Stage 1: actual run

Selected by validation MAE: **CatBoost**.

       model        MAE       RMSE        R2   n
       Dummy 100.879817 148.126404 -0.041402 109
RandomForest  86.249440 136.624412  0.114048 109
    CatBoost  80.375336 131.986525  0.173177 109

Metrics: BMP in mL CH4/g substrate VS; RMSE in same units; R2 dimensionless.
All algorithms evaluated on final holdout once for comparison; selection frozen beforehand.
One interlaboratory study, not independent-study validation. No synthetic training data.
Finite 90% group interval unavailable with this calibration laboratory count.
See data_audit.json, provenance.json, train_cv.csv, validation_metrics.csv and test_predictions.csv.