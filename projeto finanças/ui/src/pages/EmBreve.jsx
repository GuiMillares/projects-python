// Abas que já estão na navegação mas cuja tela ainda não foi construída.
//
// Um item de menu que leva a uma tela em branco parece defeito. Dizer o que
// vai existir ali custa nada e resolve.

export default function EmBreve({ titulo, descricao, icone: Icone }) {
  return (
    <>
      <div className="fin-page-head">
        <div>
          <h1 className="fin-page-title">{titulo}</h1>
          <p className="fin-page-sub">Em construção</p>
        </div>
      </div>

      <div className="fin-card">
        <div className="fin-empty">
          <Icone size={30} />
          <strong>{titulo} ainda não tem tela.</strong>
          <span style={{ maxWidth: "44ch" }}>{descricao}</span>
        </div>
      </div>
    </>
  );
}
