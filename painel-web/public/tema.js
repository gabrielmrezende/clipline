// Tema escolhido no painel (claro ou escuro), aplicado antes da primeira pintura para a tela não piscar.
// Sem escolha, vale o do sistema. Fica num arquivo à parte porque a CSP do painel só aceita script do próprio site.
(function () {
  try {
    var tema = window.localStorage.getItem("clipline.tema");
    if (tema === "claro" || tema === "escuro") document.documentElement.setAttribute("data-tema", tema);
  } catch (erro) {
    // navegador sem armazenamento: fica o tema do sistema
  }
})();
