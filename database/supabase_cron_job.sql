-- ============================================================
-- Cron job Supabase: procesamiento automatico de pedidos
-- Ejecuta la funcion public.procesar_pedidos_automaticos()
-- cada 1 minuto dentro de Supabase PostgreSQL.
-- ============================================================

create extension if not exists pg_cron with schema extensions;

-- Evita duplicar el job si vuelves a ejecutar este archivo.
select cron.unschedule(jobid)
from cron.job
where jobname = 'procesar-pedidos-automaticos';

select cron.schedule(
  'procesar-pedidos-automaticos',
  '* * * * *',
  $$select public.procesar_pedidos_automaticos();$$
);

-- Verificacion:
-- select jobid, jobname, schedule, command, active
-- from cron.job
-- where jobname = 'procesar-pedidos-automaticos';
