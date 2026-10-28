// Um documento legal (termos ou política) como a API manda: seções com
// parágrafos e, às vezes, uma lista. Usado na tela de aceite e nas páginas
// /termos e /privacidade, para os dois lugares mostrarem o mesmo texto.

export default function DocumentoTexto({ doc, versaoPorExtenso }) {
  return (
    <article className="fin-doc">
      <h1 className="fin-doc__titulo">{doc.titulo}</h1>
      {versaoPorExtenso && <p className="fin-doc__versao">Versão de {versaoPorExtenso}</p>}
      {doc.secoes.map((s) => (
        <section key={s.titulo}>
          <h2>{s.titulo}</h2>
          {s.itens.length > 0 && (
            <ul>
              {s.itens.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          {s.paragrafos.map((p) => (
            <p key={p}>{p}</p>
          ))}
        </section>
      ))}
    </article>
  );
}
