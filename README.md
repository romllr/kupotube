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
workflow na aba Actions e baixe esse artefato, extraia e abra `Kupotube.exe`.
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

Abra o servidor no navegador. Cole um link HTTPS público, busque as qualidades e baixe o vídeo. A resolução indicada corresponde à altura do arquivo; vídeos verticais podem apresentar valores diferentes dos nomes comerciais. O download escolhe a melhor faixa até a altura solicitada e inclui áudio. É possível escolher MP4, MKV ou WebM. O FFmpeg ajusta o contêiner sem recodificar o vídeo: WebM exige faixas compatíveis e pode não estar disponível; MKV aceita mais codecs. Se o site não oferecer faixas compatíveis com o formato escolhido, o app informa a falha e permite tentar outro formato.

```sh
.venv/bin/python -m pytest -q
```

Os testes usam o extrator simulado para validar qualidade, formatos, eventos de progresso, respostas, salvamento, limpeza e execução em segundo plano sem depender dos sites. Downloads reais podem exigir autenticação, sofrer bloqueios de IP ou falhar após alterações das plataformas. Esta versão não recebe cookies de usuários.

## Escopo

Versão inicial para uso local/pessoal. No desktop, o destino é escolhido antes de baixar; arquivos temporários são criados no mesmo disco e renomeados ao concluir, evitando copiar vídeos grandes. São removidos ao terminar ou falhar. A ponte JavaScript expõe somente os métodos de início e consulta de progresso; objetos internos da janela não são expostos. Downloads têm limite configurado de 2 GiB, quando o tamanho é conhecido; somente na versão de navegador o arquivo é mantido em memória antes de salvá-lo. O app Windows não carrega o vídeo inteiro na memória da interface. Antes de oferecer acesso público, adicione autenticação, limites de concorrência/armazenamento e isolamento de rede do processo yt-dlp, incluindo controle dos destinos de redirecionamentos. A validação inicial de domínio não substitui esse isolamento. Use apenas conteúdo próprio ou autorizado.

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
