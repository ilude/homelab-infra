(function () {
  "use strict";
  var SDK = window.__HERMES_PLUGIN_SDK__;
  var registry = window.__HERMES_PLUGINS__;
  if (!SDK || !registry || typeof registry.register !== "function") return;

  var React = SDK.React;
  var h = React.createElement;
  var hooks = SDK.hooks || {};
  var useState = hooks.useState;
  var useEffect = hooks.useEffect;
  var C = SDK.components || {};
  var Button = C.Button || function (props) { return h("button", props, props.children); };

  function api(path, options) {
    var request = options || {};
    request.headers = Object.assign({ "Content-Type": "application/json" }, request.headers || {});
    return SDK.fetchJSON("/api/plugins/homelab-infra-operator/" + path, request);
  }

  function InfraPage() {
    var state = useState(null);
    var result = state[0];
    var setResult = state[1];
    var busyState = useState(false);
    var busy = busyState[0];
    var setBusy = busyState[1];
    var errorState = useState("");
    var error = errorState[0];
    var setError = errorState[1];

    function run(path, options) {
      setBusy(true);
      setError("");
      api(path, options).then(setResult).catch(function (err) {
        setError(String(err.message || err));
      }).finally(function () { setBusy(false); });
    }

    useEffect(function () { run("status"); }, []);

    function apply() {
      if (!window.confirm("Apply the current reviewed homelab-infra plan?")) return;
      run("apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: "APPLY" })
      });
    }

    return h("div", { className: "p-6 max-w-4xl" },
      h("h1", { className: "text-2xl font-semibold mb-2" }, "Homelab Infra"),
      h("p", { className: "text-muted-foreground mb-6" },
        "Review validation and plans before applying infrastructure changes."),
      h("div", { className: "flex gap-2 mb-6" },
        h(Button, { disabled: busy, onClick: function () { run("status"); } }, "Status"),
        h(Button, { disabled: busy, onClick: function () { run("validate", { method: "POST" }); } }, "Validate"),
        h(Button, { disabled: busy, onClick: function () { run("plan", { method: "POST" }); } }, "Plan"),
        h(Button, { disabled: busy, onClick: apply }, "Apply reviewed plan")
      ),
      error ? h("pre", { className: "text-red-500 whitespace-pre-wrap mb-4" }, error) : null,
      result ? h("pre", { className: "bg-muted rounded p-4 whitespace-pre-wrap overflow-auto" },
        JSON.stringify(result, null, 2)) : h("p", null, "Loading…")
    );
  }

  registry.register("homelab-infra-operator", InfraPage);
})();
