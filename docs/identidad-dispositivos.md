# Identidad y nombres automáticos — v2.1

Fecha: 2026-10-24 (America/Guatemala).

Cada búsqueda validada lee ro.serialno y ro.boot.serialno, fabricante y modelo. El nombre predeterminado es **Placa SERIAL**, sin cambiar la configuración Android. Un alias manual tiene prioridad; dejarlo vacío recupera el nombre automático. La tabla muestra el serial físico separado del identificador de conexión ADB (por ejemplo IP:puerto), y permite buscar por ambos.

El serial se obtiene de propiedades declaradas por el sistema: puede faltar, ser genérico, repetirse o cambiar con una ROM. No constituye una garantía universal de identidad física. Se descartan valores genéricos o inválidos; si falta un serial utilizable se muestra Equipo seguido de una referencia al UUID interno. Cada ficha conserva su UUID completo.

Si varias fichas declaran el mismo serial, los nombres incluyen una referencia interna y se marca **Serial repetido: revisar**. Si las dos propiedades discrepan se indica **Fuentes en conflicto**. No se fusionan esas fichas automáticamente.

## Cambios de IP

Una conexión nueva se asocia a una ficha anterior solo si coinciden serial, fabricante y modelo; existe un único candidato; el serial aparece una sola vez en la búsqueda; y se confirmó que las conexiones anteriores ya no aparecen en sus servidores consultados correctamente. Si falla uno de esos criterios, se conserva una ficha independiente para revisión manual.

Si una IP ya registrada ahora declara otro serial, su estado pasa a **Identidad en conflicto**, no se sobrescribe el serial anterior y se bloquea el inventario desde esa conexión hasta revisar la asociación. Esto evita asignar silenciosamente datos de otra placa a la ficha anterior. Las conexiones históricas permanecen visibles como desconectadas, aunque una ficha ya tenga otra conexión activa; el total de conexiones guardadas puede superar el total de placas.

## Persistencia y comprobación

El esquema SQLite v3 agrega una tabla local de identidad y recupera los seriales de las capturas existentes. Antes de migrar se crea `data/granjita-antes-v3.sqlite3`. Se conservan alias y capturas. Los seriales y las bases se mantienen fuera de Git.

Pasaron 15 pruebas, incluyendo nombre automático, alias, cambio de IP, serial repetido, reutilización de IP y serial genérico. En la inspección local se encontraron también un serial compartido entre dos fichas y una conexión que declara otro serial; se marcaron para revisión. Los resultados y cantidades son una instantánea, no el inventario definitivo.

## Respaldo de avances

Por instrucción del usuario, cada avance funcional verificado debe terminar con commit y push a origin/dev2026. Esta regla está en AGENTS.md para los próximos trabajos.
