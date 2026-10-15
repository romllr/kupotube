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

Abra o servidor no navegador. Cole um link HTTPS público, busque as qualidades e baixe o vídeo. A resolução indicada corresponde à altura do arquivo; vídeos verticais podem apresentar valores diferentes dos nomes comerciais. O download escolhe a melhor faixa até a altura solicitada e inclui áudio. O contêiner final depende dos formatos disponíveis, com preferência por MP4 ao juntar faixas.

```sh
.venv/bin/python -m pytest -q
```

Os testes usam o extrator simulado para validar seleção de qualidade, respostas e limpeza de arquivos sem depender dos sites. Downloads reais podem exigir autenticação, sofrer bloqueios de IP ou falhar após alterações das plataformas. Esta versão não recebe cookies de usuários.

## Escopo

Versão inicial para uso local/pessoal. Os arquivos temporários são removidos depois da resposta. Downloads têm limite configurado de 2 GiB, quando o tamanho é conhecido; o navegador mantém o arquivo em memória antes de salvá-lo. Antes de oferecer acesso público, adicione autenticação, limites de concorrência/armazenamento e isolamento de rede do processo yt-dlp, incluindo controle dos destinos de redirecionamentos. A validação inicial de domínio não substitui esse isolamento. Use apenas conteúdo próprio ou autorizado.
