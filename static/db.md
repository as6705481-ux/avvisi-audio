# AVVISI — Documentación de Base de Datos

Versión: 0.1 (borrador vivo)
Fecha: 2025-12-26
Autor: Anthony Javier Sánchez Romero

1. Introducción

Este documento describe el modelo de datos relacional del sistema AVVISI, orientado a la gestión de:

- Clientes y contactos
- Catálogo de ítems (rentables, consumibles, servicios y bundles)
- Eventos
- Cotizaciones
- Reservas con control temporal y de capacidad

La base de datos está implementada en PostgreSQL (Supabase) y contiene reglas de negocio críticas implementadas directamente mediante constraints, índices y exclusiones temporales.

2. Visión general del modelo

2.1 Objetivo del modelo de datos

El esquema de AVVISI organiza la operación alrededor de cuatro ejes:

- Identidad y operación interna: usuarios y perfiles (profiles ligado a auth.users).
- Relación comercial: clientes y sus contactos (clients, contacts).
- Oferta: catálogo de ítems (rentables/consumibles/servicios/bundles) y su soporte operativo (activos e inventario).
- Ejecución comercial: eventos y cotizaciones que, al aceptarse, generan reservas temporales para ítems rentables.

2.2 Entidades principales y sus relaciones

Relaciones macro (nivel conceptual):

- Un cliente puede tener múltiples contactos.
- Un cliente puede tener múltiples eventos.
- Un cliente puede tener múltiples cotizaciones.
- Una cotización puede vincularse opcionalmente a un evento.
- Una cotización contiene múltiples líneas (ítems cotizados).
- Una reserva se genera a partir de una cotización aceptada, y se asocia a un ítem rentable (y opcionalmente a un asset específico).