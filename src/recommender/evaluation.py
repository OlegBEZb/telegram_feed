from sklearn.metrics import f1_score, classification_report, confusion_matrix, \
    ConfusionMatrixDisplay
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd


def eval_clf(y_test, y_pred):
    """

    Parameters
    ----------
    y_test
    y_pred

    Returns
    -------

    """
    if isinstance(y_test, (pd.core.frame.DataFrame, pd.core.series.Series)):
        y_test = y_test.astype(str)
    if isinstance(y_pred, (pd.core.frame.DataFrame, pd.core.series.Series)):
        y_pred = y_pred.astype(str)
    clf_report = classification_report(y_test,
                                       y_pred, zero_division=0)

    print(clf_report)

    test_labels = set(np.unique(y_test))
    pred_labels = set(np.unique(y_pred))
    labels = sorted(test_labels.union(pred_labels))

    conf_matrix = confusion_matrix(y_test,
                                   y_pred)
    disp = ConfusionMatrixDisplay(conf_matrix, display_labels=labels)
    fig, ax = plt.subplots(figsize=(14, 6))
    ax.grid(False)
    disp.plot(ax=ax)

    return round(f1_score(y_test, y_pred, average='micro'), 2)


def eval_on_sets(model, eval_sets):
    """
    example: {'train': (df_train, y_train),
    'test': (df_test, y_test)}
    """
    f1_dict = dict.fromkeys(eval_sets.keys())
    for name, eval_set in eval_sets.items():
        print(name)
        x, y_ground_truth = eval_set
        y_pred = model.predict(x)
        f1 = eval_clf(y_test=y_ground_truth, y_pred=pd.Series(y_pred))
        f1_dict[name] = f1
    return f1_dict
