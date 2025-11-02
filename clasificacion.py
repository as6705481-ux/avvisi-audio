# from sklearn.feature_extraction.text import CountVectorizer
# from sklearn.model_selection import train_test_split
# from sklearn.naive_bayes import MultinomialNB
# from sklearn.metrics import accuracy_score, classification_report
# import pandas as pd

# # Lista básica de stopwords en español
# stopwords_es = [
#     "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las", "por",
#     "un", "para", "con", "no", "una", "su", "al", "lo", "como", "más", "pero",
#     "sus", "le", "ya", "o", "fue", "este", "ha", "sí", "porque", "esta", "entre"
# ]

# # Cargar el CSV
# df = pd.read_csv("clasificacion_arancelaria.csv", encoding="utf-8")
# df = df.dropna(subset=["POSICION_ARANCELARIA", "DESCRIPCION_MERCANCIA"])
# df["DESCRIPCION_MERCANCIA"] = df["DESCRIPCION_MERCANCIA"].str.lower()

# # Agrupar la posición a 4 dígitos
# df["POSICION_4D"] = df["POSICION_ARANCELARIA"].astype(str).str[:4]

# # Tomar muestra
# df_sample = df.sample(n=199999, random_state=42)

# # Separar entrenamiento y prueba
# X_train, X_test, y_train, y_test = train_test_split(
#     df_sample["DESCRIPCION_MERCANCIA"], df_sample["POSICION_4D"], test_size=0.2, random_state=42
# )

# # Vectorización
# vectorizer = CountVectorizer(stop_words=stopwords_es, max_features=3000)  # max_features opcional
# X_train_vec = vectorizer.fit_transform(X_train)
# X_test_vec = vectorizer.transform(X_test)

# # Entrenar modelo
# modelo = MultinomialNB()
# modelo.fit(X_train_vec, y_train)

# # Evaluación
# y_pred = modelo.predict(X_test_vec)
# print("Precisión:", accuracy_score(y_test, y_pred))
# print("Reporte por capítulo (4 dígitos):\n", classification_report(y_test, y_pred))


# nueva = ["ROPA USADA"]
# nueva_vec = vectorizer.transform(nueva)
# print("Predicción para nueva descripción:", modelo.predict(nueva_vec)[0])


# import pandas as pd
# from sklearn.model_selection import train_test_split
# from sklearn.feature_extraction.text import CountVectorizer
# from xgboost import XGBClassifier
# from sklearn.metrics import accuracy_score, classification_report

# # Stopwords en español
# stopwords_es = [
#     "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las", "por",
#     "un", "para", "con", "no", "una", "su", "al", "lo", "como", "más", "pero",
#     "sus", "le", "ya", "o", "fue", "este", "ha", "sí", "porque", "esta", "entre"
# ]

# # 1. Cargar datos
# df = pd.read_csv("clasificacion_arancelaria.csv", encoding="utf-8")
# df = df.dropna(subset=["POSICION_ARANCELARIA", "DESCRIPCION_MERCANCIA"])
# df["DESCRIPCION_MERCANCIA"] = df["DESCRIPCION_MERCANCIA"].str.lower()
# df["POSICION_4D"] = df["POSICION_ARANCELARIA"].astype(str).str[:4]

# # 2. Muestra manejable (puedes reducir a 50,000 si da problemas de RAM)
# df_sample = df.sample(n=100000, random_state=42)



# from sklearn.preprocessing import LabelEncoder

# # 1. Codificar todo antes de dividir
# le = LabelEncoder()
# df_sample["CLASE_ENCODED"] = le.fit_transform(df_sample["POSICION_4D"])

# # 2. Separar después de codificar
# X_train, X_test, y_train_enc, y_test_enc = train_test_split(
#     df_sample["DESCRIPCION_MERCANCIA"],
#     df_sample["CLASE_ENCODED"],
#     test_size=0.2,
#     random_state=42
# )

# # 3. Vectorizar
# vectorizer = CountVectorizer(stop_words=stopwords_es, max_features=3000)
# X_train_vec = vectorizer.fit_transform(X_train)
# X_test_vec = vectorizer.transform(X_test)

# # 4. Entrenar XGBoost
# modelo = XGBClassifier(
#     objective='multi:softmax',
#     num_class=len(le.classes_),  # correcto
#     eval_metric='mlogloss',
#     use_label_encoder=False,
#     verbosity=0
# )

# modelo.fit(X_train_vec, y_train_enc)

# # 5. Predicción
# y_pred_enc = modelo.predict(X_test_vec)
# y_pred = le.inverse_transform(y_pred_enc)
# y_test_true = le.inverse_transform(y_test_enc)

# # 6. Evaluación
# from sklearn.metrics import accuracy_score, classification_report
# # 7. Exportar a CSV con resultados
# df_resultados = pd.DataFrame({
#     "DESCRIPCION_MERCANCIA": X_test.values,
#     "CLASE_REAL": y_test_true,
#     "CLASE_PREDICHA": y_pred
# })

# df_resultados.to_csv("resultados_clasificacion.csv", index=False, encoding="utf-8-sig")
# print("Archivo 'resultados_clasificacion.csv' generado correctamente.")

