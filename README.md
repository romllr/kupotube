# Kupotube

## Aplicativo para Windows

A versão empacotada foi preparada para Windows x64: `Kupotube.exe` inclui Python,
FFmpeg e Node.js e exibe a interface dentro de sua própria janela, usando pywebview
com WebView2. Não abre uma aba do navegador. Clique em baixar e escolha onde salvar
na janela nativa do Windows. Fechar a janela do app encerra o servidor local.
O WebView2 Runtime, normalmente presente no Windows 10/11 atualizado, é necessário.
O executável é um único arquivo; na execução, extrai suas dependências internamente.

O executável precisa ser compilado em Windows. O workflow **Gerar Kupotube para
Windows**, em GitHub Actions, instala as dependências, executa os testes, compila
com PyInstaller e verifica se o executável serve a interface antes de anexar o
artefato **Kupotube-Windows-x64**. Após enviar estes arquivos ao GitHub, execute o
workflow na aba Actions e baixe esse artefato, extraia e abra `Kupotube.exe`. Após a compilação e verificações, o workflow também publica o executável e seu manifesto em GitHub Releases.
Esta preparação não significa que a compilação em Windows já foi executada.

O executável não é assinado digitalmente. O primeiro início pode demorar enquanto
as ferramentas são extraídas para uma pasta temporária. Acesso à internet continua
necessário para consultar e baixar os vídeos.

App web em português para baixar vídeos com yt-dlp, com tema Catppuccin Macchiato e seleção das resoluções fornecidas pela plataforma. YouTube/Shorts, TikTok, Pinterest e Instagram Reels são aceitos; disponibilidade depende do extrator e das restrições do site.

## Rodar localmente

Requer Python 3.12+ e FFmpeg no PATH.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
```

Abra o servidor no navegador. Cole um link HTTPS público, busque as qualidades e baixe o vídeo. A resolução indicada corresponde à altura do arquivo; vídeos verticais podem apresentar valores diferentes dos nomes comerciais. O download escolhe a melhor faixa até a altura solicitada e inclui áudio. É possível escolher MP4, MKV, WebM ou MP3 (somente áudio a 192 kbps). O FFmpeg ajusta o contêiner sem recodificar o vídeo: WebM exige faixas compatíveis e pode não estar disponível; MKV aceita mais codecs. Se o site não oferecer faixas compatíveis com o formato escolhido, o app informa a falha e permite tentar outro formato.

```sh
.venv/bin/python -m pytest -q
```

Os testes usam o extrator simulado para validar qualidade, formatos, eventos de progresso, respostas, salvamento, limpeza e execução em segundo plano sem depender dos sites. Downloads reais podem exigir autenticação, sofrer bloqueios de IP ou falhar após alterações das plataformas. No app Windows, é possível importar uma sessão local por arquivo de cookies Netscape (.txt); apenas cookies das plataformas compatíveis são mantidos, e o arquivo original não é alterado. Não compartilhe arquivos de sessão.

## Escopo

Versão inicial para uso local/pessoal. No desktop, o destino é escolhido antes de baixar; arquivos temporários são criados no mesmo disco e renomeados ao concluir, evitando copiar vídeos grandes. São removidos ao terminar ou falhar. A ponte JavaScript expõe métodos de download, sessão, preferências e atualização; objetos internos da janela não são expostos. Downloads têm limite configurado de 2 GiB, quando o tamanho é conhecido; somente na versão de navegador o arquivo é mantido em memória antes de salvá-lo. O app Windows não carrega o vídeo inteiro na memória da interface. Antes de oferecer acesso público, adicione autenticação, limites de concorrência/armazenamento e isolamento de rede do processo yt-dlp, incluindo controle dos destinos de redirecionamentos. A validação inicial de domínio não substitui esse isolamento. Use apenas conteúdo próprio ou autorizado.

## Progresso e avisos

O download do app Windows roda em uma tarefa separada, com consulta de progresso
pela interface a cada 350 ms. O percentual corresponde à faixa atual (vídeo ou
áudio); faixas separadas podem começar novamente em 0%. Quando o tamanho não é
conhecido, a barra fica indeterminada; estimativas aparecem com ≈. A junção e o
ajuste de formato têm indicação própria, sem inventar um percentual de FFmpeg.
A conclusão só é sinalizada depois que o arquivo foi salvo no destino.

Ao concluir, há um aviso no canto inferior direito **dentro do app** e um som suave.
O botão de alto-falante permite desativar o som, com preferência lembrada.
Os ícones Phosphor estão incluídos localmente (licença em `static/icons/LICENSE`),
sem depender de CDN. O ícone Windows inclui a silhueta YouTube em Macchiato.
A inicialização do executável único ainda exige a extração interna das dependências;
isso pode levar alguns segundos, especialmente com antivírus ativo.

Teste adicional da interface (requer Playwright e Chromium ou Edge): com o servidor
em `127.0.0.1:8010`, execute `python tests/ui_smoke.py`. O workflow Windows também
executa esse teste com o Edge, usando eventos de download simulados.

## Atualizações automáticas

A partir da versão 0.3.0, o app consulta a última release pública de
`romllr/kupotube` ao abrir e pelo botão **Verificar atualizações**. Quando há uma
versão superior, **Atualizar e reiniciar** baixa o executável em segundo plano,
confere tamanho, SHA-256 e o cabeçalho Windows, espera o app encerrar, mantém um
backup durante a substituição e reinicia. Se a substituição falhar, restaura a
versão anterior. Sessão e preferência de som ficam em `%LOCALAPPDATA%/Kupotube`,
fora do executável; não são incluídas nem sobrescritas na atualização.

O usuário precisa ter permissão de escrita na pasta onde salvou o executável.
O mecanismo verifica a integridade do arquivo publicado por HTTPS; o binário
continua sem assinatura Authenticode. A recuperação cobre falha de substituição
ou de início do processo, não um defeito funcional de uma versão que iniciou.

**O repositório e suas releases precisam estar públicos** para o atualizador
funcionar sem pedir credenciais. Não inclua tokens pessoais no aplicativo.
A API do GitHub deste ambiente recusou alterar/consultar a visibilidade; o dono
precisa confirmar `Public` em Settings → General → Danger Zone no GitHub.

Para publicar a próxima versão, incremente `VERSION` em `version.py`, atualize
`RELEASE_NOTES.md` e envie para `main`. O workflow testa, compila e publica uma
release nova com `Kupotube.exe` e `update.json`. Releases já publicadas não são
substituídas. Habilite permissões de escrita em Actions se a política da conta
impedir a publicação. Usuários das versões anteriores a 0.3.0 precisam baixar
esta versão manualmente uma vez; versões futuras usarão o atualizador.

O teste de substituição/recuperação executa PowerShell apenas em Windows; é
ignorado em Linux. Os testes locais também cobrem integridade, rejeição de origem
inválida, ausência de downgrade, interface de atualização e persistência de sessão.

## TikTok e Instagram

O pacote inclui `curl-cffi`, usado pelos extratores para compatibilidade com as
requisições desses sites. Há preferência por faixas TikTok não marcadas como
`watermarked`, com fallback para as faixas disponíveis. Isso não remove uma marca
embutida na imagem e não garante que toda publicação tenha versão sem marca.
Vídeos sem resolução informada usam a opção Original em vez de serem rejeitados.
Erros de login, bloqueio, limite e formato indisponível têm mensagens específicas.
Se o site exigir login, importe uma sessão da sua própria conta pelo app; não há
leitura automática dos navegadores. A importação de sessão não contorna restrições
de acesso da plataforma. Os downloads dos dois links de exemplo fornecidos pelo
usuário e a extração de MP3 foram validados nesta instância com FFprobe.
