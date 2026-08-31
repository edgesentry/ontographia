document$.subscribe(function () {
  mermaid.initialize({ startOnLoad: false });
  mermaid.run({ querySelector: ".mermaid" });
});
