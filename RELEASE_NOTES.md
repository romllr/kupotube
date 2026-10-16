Kupotube 0.3.7

- Recortes agora baixam o original com yt-dlp e cortam localmente com FFmpeg, sem buscar o trecho diretamente em faixas remotas.
- Faixa de vídeo obrigatória nos recortes MP4, MKV e WebM; falha explícita se a origem não contiver vídeo.
- Mensagens de erro identificam a plataforma e informam o motivo da falha.
- O download do original antes do recorte pode aumentar o tempo de espera e o uso temporário de disco.
