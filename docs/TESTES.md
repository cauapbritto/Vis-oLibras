# Testes do Librahin

## 1. Testes automáticos

Não precisam de webcam: usam landmarks simulados (`tests/sinteticos.py`), câmeras e
motores de voz falsos. Rodar (modo desenvolvimento):

```bash
pip install -r requirements-dev.txt
pytest                 # todos
pytest -v tests/test_estabilizador.py   # um arquivo, com o nome de cada teste
```

Os testes com o MediaPipe real (`test_extrator.py`) baixam uma foto de exemplo; sem
internet, eles são pulados (aparecem como "skipped"), sem falhar.

| O que é testado | Arquivo | Exemplos de casos |
|---|---|---|
| Normalização dos landmarks | `test_features.py` | mesmo vetor com a pessoa em outro lugar, mais longe da câmera ou com a mão maior; posição no corpo e formato da mão mudam o vetor |
| Tamanho dos vetores | `test_features.py`, `test_config.py` | sempre `TAM_FEATURES_JANELA` com câmeras de 13, 30 e 60 fps; v1 é o início da v2 |
| Uma mão | `test_features.py` | só a direita; só a esquerda (blocos e flags corretos) |
| Duas mãos | `test_features.py`, `test_temporal.py` | os dois blocos preenchidos, flags [1, 1], distância entre as mãos |
| Mão ausente | `test_features.py`, `test_temporal.py` | zeros + flag 0; falha curta interpolada, longa não; sem mãos o vetor existe |
| Coleta = tempo real | `test_features.py` | amostra gravada e buffer do tempo real geram exatamente o mesmo vetor |
| Movimento | `test_temporal.py` | parado = movimento zero; sobe × desce; aceno; abrir a mão; tremor não conta |
| Carregamento do modelo | `test_classificador.py` | salvar/carregar; modelo ausente; features incompatíveis; modelo v1 continua funcionando; avisos de classes |
| Classificação | `test_classificador.py`, `test_reconhecedor.py` | probabilidades somam 1; fluxo completo com landmarks simulados; aceno × mão parada no mesmo lugar |
| Estabilidade temporal | `test_estabilizador.py`, `test_reconhecedor.py` | NOME ×5 → um NOME; sinal segurado por 10 s → uma palavra; confiança baixa; "piscadas" |
| Cooldown | `test_estabilizador.py` | cooldown geral; cooldown da mesma palavra; liberação (_NADA) |
| Montagem da frase | `test_frase.py` | EU NOME CAUA; quatro estados separados; pausa; frase cheia; regras plugáveis; português + glosa com tabela |
| Tabela de frases | `test_traducao.py` | frase mais longa ganha; trechos sem frase ficam em glosa; maiúsculas; avisos com número da linha; UTF-8/ANSI/arquivo ausente; `frases.txt` do projeto sem avisos |
| Palavras repetidas | `test_frase.py`, `test_estabilizador.py` | repetição involuntária ignorada; intencional aceita |
| Limpeza da frase | `test_frase.py`, `test_reconhecedor.py` | remover a última; limpar tudo; limpar zera buffer e estabilizador |
| Voz | `test_voz.py` | texto vazio; fala em andamento (ignorar/enfileirar); sem sistema de voz; erro de áudio com recuperação |
| Câmera e threads | `test_camera.py`, `test_captura.py` | câmera indisponível; falhas momentâneas; nenhuma palavra perdida entre threads; parada limpa |
| Dataset e treino | `test_dataset.py`, `test_treino.py` | validação de amostras; inconsistências; treino reprodutível |
| Testes controlados | `test_experimento.py` | tempos medidos; erro; tempo esgotado; descarte; resumo conferido à mão; nada é inventado |
| Separação dos modos | `test_modos.py` | a aplicação não importa nada de treino; pacote de demonstração só com o necessário |

## 2. Checklist manual

Faça com a **mesma máquina, câmera e local** da apresentação. Marque cada item.

### Câmera
- [ ] `python scripts/desenvolvimento/testar_deteccao.py` abre a imagem em até ~5 s
- [ ] A imagem aparece espelhada (levantar a mão direita = mão do lado direito da tela)
- [ ] Só a mão direita → "Mao direita" em verde (se aparecer trocado, `NOMES_MAOS_INVERTIDOS = False` no `config.py`)
- [ ] Só a esquerda → "Mao esquerda"; as duas → "Ambas as maos"
- [ ] FPS ≥ 15
- [ ] Tirar o cabo USB / cobrir a câmera: aparece mensagem de erro, sem travar
- [ ] Com Zoom/Teams usando a câmera: mensagem clara de câmera em uso

### Reconhecimento
- [ ] "Modelo com 10 sinais" com ponto verde na barra de baixo (amarelo = faltam sinais no modelo)
- [ ] Cada sinal do vocabulário é reconhecido em pelo menos 4 de 5 tentativas
- [ ] Segurar um sinal por 5 s gera **uma** palavra
- [ ] Abaixar as mãos e repetir o sinal gera a segunda palavra
- [ ] 1 minuto conversando e gesticulando sem sinalizar gera no máximo 1 palavra
- [ ] O tempo entre terminar o sinal e a palavra aparecer é ≤ ~1 s

### Iluminação
- [ ] Luz de frente para a pessoa (evitar janela ou lâmpada atrás)
- [ ] Landmarks estáveis, sem "piscar", nas mãos e nos ombros
- [ ] Testar com a luz do local da apresentação (auditório costuma ser mais escuro)
- [ ] Fundo sem outras pessoas passando

### Distância
- [ ] Pessoa a ~1 m da câmera, com **ombros e mãos** visíveis
- [ ] "Ombros não visíveis" não aparece durante os sinais
- [ ] A 0,6 m e a 1,5 m o reconhecimento ainda funciona (a normalização compensa a distância)
- [ ] Sinais feitos perto do rosto (OBRIGADO, BOM) não saem da imagem

### Sinais
- [ ] Todos fazem os sinais como descrito em `docs/SINAIS.md`
- [ ] Pares parecidos (EU × MEU) testados lado a lado
- [ ] Sinais com movimento (OI, AJUDA…) testados em velocidade normal e mais lenta
- [ ] Testado por uma pessoa que **não** gravou o dataset

### Voz
- [ ] "Voz: <nome da voz>" com ponto verde na barra de baixo (ex.: Microsoft Maria)
- [ ] Finalizar uma frase fala em português (não em inglês)
- [ ] Volume do computador/caixa de som ajustado para o local
- [ ] Pedir "Reproduzir voz" duas vezes seguidas não trava (a segunda é ignorada com aviso)
- [ ] Sem alto-falante/áudio: a interface continua funcionando

### Interface
- [ ] Ao abrir, a janela aparece logo com "Carregando" e o botão Iniciar câmera é liberado em poucos segundos
- [ ] Ícone do Librahin (mão azul) na janela, na barra de tarefas e no atalho da Área de Trabalho
- [ ] Iniciar câmera → imagem com landmarks; Parar câmera → volta a "Câmera desligada"
- [ ] Sem câmera (ou com ela ocupada pelo Teams/Zoom), o painel explica o erro e a barra de baixo mostra "Câmera com erro"
- [ ] O botão Sobre mostra a equipe, o orientador e o curso; Esc ou Fechar fecha
- [ ] Iniciar/parar 3 vezes seguidas sem travar
- [ ] Remover última palavra, Limpar frase e Finalizar frase funcionam (e os atalhos Backspace, C, Espaço)
- [ ] "Sinal detectado", "Último sinal confirmado", "Frase em construção" e "Frase final" mudam como esperado
- [ ] Com "Falar cada palavra" ligado, cada palavra é falada logo que aparece; desligado, a frase é falada ao finalizar
- [ ] Medidor de confiança azul acima de 75% e amarelo abaixo, com o texto "Acima/Abaixo do limite"
- [ ] Uma frase cadastrada no `frases.txt` (ex.: BOM DIA) aparece em português na prévia e na frase final, com "Sinais: ..." embaixo, e é falada em português
- [ ] Uma sequência sem frase cadastrada continua aparecendo como glosa
- [ ] Fechar a janela com a câmera ligada encerra o programa e libera a câmera
- [ ] 10 minutos ligada sem travar nem ficar lenta
