// Preparo da foto de perfil antes de subir.
//
// O recorte e a redução acontecem aqui, no navegador: uma foto de celular
// tem 4MB e 4000px, e o que a tela mostra é um círculo de 30px. Mandar o
// arquivo original para o banco seria guardar 100x mais bytes do que se usa.

const TIPOS_ACEITOS = ["image/jpeg", "image/png", "image/webp"];
const TAMANHO_MAX_ARQUIVO = 12 * 1024 * 1024;

export class ImagemInvalida extends Error {}

/**
 * Recorta a imagem no quadrado central e reduz para `lado`px.
 *
 * O recorte central evita a distorção que apareceria ao espremer uma foto
 * retangular dentro do avatar redondo.
 *
 * @returns {Promise<string>} data URL JPEG pronta para enviar
 */
export async function prepararFotoPerfil(file, lado = 256) {
  if (!file) throw new ImagemInvalida("Nenhum arquivo escolhido.");
  if (!TIPOS_ACEITOS.includes(file.type)) {
    throw new ImagemInvalida("Use uma imagem JPEG, PNG ou WebP.");
  }
  if (file.size > TAMANHO_MAX_ARQUIVO) {
    throw new ImagemInvalida("Imagem muito grande (máximo 12MB).");
  }

  let bitmap;
  try {
    // imageOrientation "from-image" respeita o EXIF: sem isso, foto tirada
    // com o celular deitado chega girada 90 graus.
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new ImagemInvalida("Não consegui ler essa imagem.");
  }

  try {
    const menor = Math.min(bitmap.width, bitmap.height);
    const x = (bitmap.width - menor) / 2;
    const y = (bitmap.height - menor) / 2;

    const canvas = document.createElement("canvas");
    canvas.width = lado;
    canvas.height = lado;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bitmap, x, y, menor, menor, 0, 0, lado, lado);

    // JPEG e não PNG: para foto, o PNG sai várias vezes maior sem ganho
    // visível. A transparência não faz falta num avatar recortado.
    return canvas.toDataURL("image/jpeg", 0.85);
  } finally {
    bitmap.close?.();
  }
}
