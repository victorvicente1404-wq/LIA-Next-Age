export default function App() {
  return (
    <main className="shell">
      <section className="panel" aria-labelledby="lia-title">
        <div className="status"><span className="status-dot" /> Núcleo local em preparação</div>
        <h1 id="lia-title">Olá. Eu sou a Lia.</h1>
        <p>
          Sua assistente pessoal está sendo construída para funcionar primeiro no seu próprio
          dispositivo, com memória independente e ferramentas sob seu controle.
        </p>
        <div className="capabilities">
          <div><strong>IA local</strong><span>Sem cotas de provedores como requisito</span></div>
          <div><strong>Memória própria</strong><span>Separada do modelo de linguagem</span></div>
          <div><strong>Lia Dev</strong><span>Alterações revisáveis e aprovadas por você</span></div>
        </div>
        <small>Versão de fundação · interface inicial</small>
      </section>
    </main>
  );
}
