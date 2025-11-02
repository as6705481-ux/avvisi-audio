import mysql.connector
from mysql.connector import Error

# Función para establecer la conexión a la base de datos
def conectar_bd():
    try:
        con = mysql.connector.connect(
            host="avissi.cfk4swoq2ax5.us-east-1.rds.amazonaws.com",
            user="admin",
            password="24junio98",
            database="avvisi",
            port=3306
        )
        if con.is_connected():
            return con
    except Error as e:
        print(f"Error de conexión: {e}")
        return None

# Función para obtener las categorías de productos
def obtener_categorias():
    con = conectar_bd()
    if con:
        try:
            cursor = con.cursor(dictionary=True)
            query = "SELECT DISTINCT category FROM Inventory"
            cursor.execute(query)
            categorias = cursor.fetchall()
            cursor.close()
            con.close()
            # Extrae solo los nombres de las categorías en una lista
            return [categoria["category"] for categoria in categorias]
        except Error as e:
            print(f"Error al ejecutar la consulta: {e}")
            return None
    else:
        print("Error de conexión a la base de datos")
        return None
######################################################
# Función para obtener productos por categoría
def obtener_productos_por_categoria(categoria):
    if not categoria:  # Verifica si la categoría es nula o vacía
        return []

    con = conectar_bd()
    if con:
        try:
            cursor = con.cursor(dictionary=True)
            # Consulta con la categoría como parámetro para evitar SQL injection
            query = "SELECT product_id, product_name, stock, unit_price, provider_id FROM Inventory WHERE category = %s"
            cursor.execute(query, (categoria,))
            productos = cursor.fetchall()
            cursor.close()
            con.close()
            # Asegúrate de que las columnas numéricas estén en el formato adecuado
            for producto in productos:
                producto["stock"] = float(producto["stock"])
                producto["unit_price"] = float(producto["unit_price"])
            return productos
        except Error as e:
            print(f"Error al ejecutar la consulta: {e}")
            return None
    else:
        print("Error de conexión a la base de datos")
        return None
    
########################################  
# Función para obtener todos los clientes
def obtener_clientes():
    con = conectar_bd()
    if con:
        try:
            cursor = con.cursor(dictionary=True)
            query = "SELECT client_id, name, rtn FROM Clients"  # Consulta para obtener clientes
            cursor.execute(query)
            clientes = cursor.fetchall()
            cursor.close()
            con.close()
            return clientes  # Devuelve los datos en formato de lista de diccionarios
        except Error as e:
            print(f"Error al ejecutar la consulta: {e}")
            return None
    else:
        print("Error de conexión a la base de datos")
        return None