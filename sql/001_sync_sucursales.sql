-- Ejecutar UNA VEZ en la base MySQL de Casa Central.
-- Los errores locales continúan con sincronizado = 0 y campos de origen en NULL.
-- Los errores importados desde sucursales se insertan con sincronizado = 1.

ALTER TABLE sys_errores
    ADD COLUMN sincronizado TINYINT(1) NOT NULL DEFAULT 0 AFTER tablas_abiertas,
    ADD COLUMN id_sucursal_origen INT NULL AFTER sincronizado,
    ADD COLUMN id_error_origen INT NULL AFTER id_sucursal_origen,
    ADD COLUMN fecha_sincronizacion DATETIME NULL AFTER id_error_origen,
    ADD UNIQUE KEY uq_error_origen (id_sucursal_origen, id_error_origen),
    ADD KEY idx_sucursal_origen (id_sucursal_origen),
    ADD KEY idx_sincronizado (sincronizado),
    ADD KEY idx_fecha_sincronizacion (fecha_sincronizacion);

-- Opcional: relación lógica con sucursales. No se agrega FK para no acoplar
-- el funcionamiento histórico de FASA ni impedir conservar errores de una
-- sucursal que eventualmente sea eliminada/desactivada.
