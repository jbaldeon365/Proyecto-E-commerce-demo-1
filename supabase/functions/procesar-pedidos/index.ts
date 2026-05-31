const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

  if (!supabaseUrl || !serviceKey) {
    return new Response(
      JSON.stringify({ error: "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY." }),
      { status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" } },
    );
  }

  const rpcResponse = await fetch(`${supabaseUrl}/rest/v1/rpc/procesar_pedidos_automaticos`, {
    method: "POST",
    headers: {
      apikey: serviceKey,
      authorization: `Bearer ${serviceKey}`,
      "Content-Type": "application/json",
      prefer: "return=representation",
    },
    body: "{}",
  });

  const body = await rpcResponse.text();

  return new Response(body || "[]", {
    status: rpcResponse.status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
});
