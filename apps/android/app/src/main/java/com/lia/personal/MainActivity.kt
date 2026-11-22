package com.lia.personal

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.lia.personal.data.LiaStoreProvider
import com.lia.personal.inference.ImportedModel
import com.lia.personal.inference.InferenceStatus
import com.lia.personal.inference.LiaInferenceEngine
import com.lia.personal.inference.LiaModelStore
import com.lia.personal.inference.LiaPromptMessage
import com.lia.personal.inference.LlamaCppInferenceEngine
import com.lia.personal.inference.ModelImportException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                LiaApp()
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LiaApp() {
    val context = LocalContext.current
    val storage = remember { LiaStoreProvider(context.applicationContext) }
    val repository = storage.repository
    val modelStore = remember {
        LiaModelStore(
            contentResolver = context.contentResolver,
            modelsDirectory = context.filesDir.resolve("models"),
        )
    }
    val inferenceEngine: LiaInferenceEngine = remember { LlamaCppInferenceEngine(context.applicationContext) }
    val inferenceStatus by inferenceEngine.status.collectAsState()
    val scope = rememberCoroutineScope()

    var storageReady by remember { mutableStateOf(false) }
    var storageError by remember { mutableStateOf(false) }
    var conversationCount by remember { mutableIntStateOf(0) }
    var conversationId by remember { mutableStateOf<String?>(null) }
    var importingModel by remember { mutableStateOf(false) }
    var loadingModel by remember { mutableStateOf(false) }
    var modelStatus by remember { mutableStateOf("Verificando modelos locais…") }
    var importedModels by remember { mutableStateOf<List<ImportedModel>>(emptyList()) }
    var draft by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var chatLines by remember { mutableStateOf<List<Pair<String, String>>>(emptyList()) }

    val runtimeReady = inferenceStatus is InferenceStatus.Ready
    val runtimeLabel = when (val state = inferenceStatus) {
        InferenceStatus.Unavailable -> "Motor local aguardando um modelo."
        InferenceStatus.Loading -> "Carregando modelo no processador…"
        InferenceStatus.Generating -> "Lia está pensando…"
        is InferenceStatus.Ready -> "Motor llama.cpp pronto • ${state.modelName}"
        is InferenceStatus.Failed -> when (state.diagnosticCode) {
            "NATIVE_LIBRARY_UNAVAILABLE" -> "Biblioteca nativa indisponível nesta instalação."
            "INSUFFICIENT_MEMORY" -> "Memória RAM livre insuficiente para carregar este modelo com segurança."
            else -> "Não foi possível iniciar o motor (${state.diagnosticCode})."
        }
    }

    val modelPicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri != null) {
            importingModel = true
            modelStatus = "Importando modelo para o armazenamento privado…"
            scope.launch {
                try {
                    val catalog = withContext(Dispatchers.IO) {
                        modelStore.importModel(uri)
                        modelStore.listImportedModels()
                    }
                    importedModels = catalog
                    modelStatus = "Catálogo local atualizado. Selecione Carregar para iniciar o motor."
                } catch (error: ModelImportException) {
                    modelStatus = when (error.diagnosticCode) {
                        "MODEL_TOO_LARGE" -> "O modelo excede o limite de 3 GB."
                        "INSUFFICIENT_SPACE" -> "Não há espaço livre suficiente para importar o modelo."
                        "INVALID_GGUF" -> "O arquivo selecionado não tem uma assinatura GGUF válida."
                        "SOURCE_PERMISSION_DENIED" -> "O Android não permitiu ler o arquivo selecionado."
                        "SOURCE_UNAVAILABLE" -> "Não foi possível abrir o arquivo selecionado."
                        "SOURCE_SIZE_MISMATCH" -> "O tamanho recebido não corresponde ao informado pelo arquivo."
                        "STORAGE_UNAVAILABLE" -> "O armazenamento privado da Lia não está disponível."
                        else -> "A importação falhou (${error.diagnosticCode})."
                    }
                } catch (_: Exception) {
                    modelStatus = "Não foi possível importar o modelo. Tente selecionar o arquivo novamente."
                } finally {
                    importingModel = false
                }
            }
        }
    }

    LaunchedEffect(storage) {
        try {
            val initialState = withContext(Dispatchers.IO) {
                val conversations = repository.listConversations()
                val active = conversations.firstOrNull() ?: repository.createConversation("Conversa inicial")
                Triple(
                    active.id,
                    repository.listConversations().size,
                    repository.getMessages(active.id, 100).map { it.role to it.content },
                ) to modelStore.listImportedModels()
            }
            conversationId = initialState.first.first
            conversationCount = initialState.first.second
            chatLines = initialState.first.third
            importedModels = initialState.second
            modelStatus = if (importedModels.isEmpty()) {
                "Nenhum modelo local importado."
            } else {
                "${importedModels.size} modelo(s) encontrado(s) no armazenamento privado."
            }
            storageReady = true
        } catch (_: Exception) {
            storageError = true
            modelStatus = "Não foi possível verificar o catálogo local de modelos."
        }
    }

    DisposableEffect(storage, inferenceEngine) {
        onDispose {
            inferenceEngine.cancelGeneration()
            storage.close()
        }
    }

    fun loadModel(model: ImportedModel) {
        scope.launch {
            loadingModel = true
            modelStatus = "Preparando o modelo para execução local…"
            try {
                inferenceEngine.loadModel(model.file)
                modelStatus = "Modelo carregado. A conversa local está habilitada."
            } catch (_: Exception) {
                modelStatus = "Falha ao carregar o modelo. Confira se ele é compatível e cabe na memória disponível."
            } finally {
                loadingModel = false
            }
        }
    }

    fun createNewConversation() {
        if (sending) return
        scope.launch {
            try {
                val conversation = withContext(Dispatchers.IO) {
                    repository.createConversation("Nova conversa")
                }
                conversationId = conversation.id
                chatLines = emptyList()
                conversationCount = withContext(Dispatchers.IO) {
                    repository.listConversations().size
                }
            } catch (_: Exception) {
                modelStatus = "Não foi possível criar uma nova conversa local."
            }
        }
    }

    fun sendMessage() {
        val clean = draft.trim()
        val activeId = conversationId
        if (clean.isEmpty() || activeId == null || !runtimeReady || sending) return

        draft = ""
        sending = true
        chatLines = chatLines + ("user" to clean)
        scope.launch {
            val response = StringBuilder()
            try {
                withContext(Dispatchers.IO) {
                    repository.appendMessage(activeId, "user", clean)
                }
                val history = withContext(Dispatchers.IO) {
                    repository.getMessages(activeId, 24)
                }
                val prompt = buildList {
                    add(
                        LiaPromptMessage(
                            LiaPromptMessage.Role.SYSTEM,
                            "Você é Lia, uma assistente pessoal útil, cuidadosa e direta. Responda em português brasileiro quando o usuário falar português. Seja honesta sobre limites e não afirme ter executado ações que não executou.",
                        ),
                    )
                    history.forEach { message ->
                        val role = when (message.role) {
                            "system" -> LiaPromptMessage.Role.SYSTEM
                            "assistant" -> LiaPromptMessage.Role.ASSISTANT
                            else -> LiaPromptMessage.Role.USER
                        }
                        add(LiaPromptMessage(role, message.content))
                    }
                }
                inferenceEngine.generate(prompt, 160).collect { token ->
                    response.append(token)
                    val lastLine = chatLines.lastOrNull()
                    chatLines = if (lastLine?.first == "assistant") {
                        chatLines.dropLast(1) + ("assistant" to response.toString())
                    } else {
                        chatLines + ("assistant" to response.toString())
                    }
                }
                if (response.isNotBlank()) {
                    withContext(Dispatchers.IO) {
                        repository.appendMessage(activeId, "assistant", response.toString())
                    }
                } else {
                    chatLines = chatLines + ("assistant" to "Não consegui gerar uma resposta. Tente novamente ou escolha outro modelo.")
                }
            } catch (_: Exception) {
                chatLines = chatLines + ("assistant" to "Ocorreu um erro durante a geração local. Sua mensagem continua salva no histórico.")
            } finally {
                sending = false
                conversationCount = withContext(Dispatchers.IO) { repository.listConversations().size }
            }
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Lia")
                        Text(
                            text = "Assistente pessoal local",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
            )
        },
    ) { contentPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(contentPadding)
                .padding(horizontal = 16.dp, vertical = 12.dp),
        ) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(18.dp),
                color = MaterialTheme.colorScheme.surfaceContainer,
            ) {
                Column(modifier = Modifier.padding(14.dp)) {
                    Text(
                        text = when {
                            storageReady -> "Armazenamento local preparado"
                            storageError -> "Não foi possível abrir o armazenamento local"
                            else -> "Preparando armazenamento local…"
                        },
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Spacer(modifier = Modifier.height(5.dp))
                    Text(
                        text = if (storageReady) {
                            "$conversationCount conversa(s) guardada(s) neste aparelho. Histórico e memórias explícitas ficam no armazenamento privado. Nenhuma mensagem é enviada para um serviço remoto."
                        } else {
                            "Histórico de conversas e memórias explícitas ficam separados no próprio aparelho."
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))
            Text("Motor local", style = MaterialTheme.typography.titleMedium)
            Text(runtimeLabel, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(modifier = Modifier.height(6.dp))
            Text(modelStatus, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)

            importedModels.forEach { model ->
                Spacer(modifier = Modifier.height(6.dp))
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerLow,
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(model.originalName, style = MaterialTheme.typography.bodySmall)
                            Text(
                                "${model.sizeBytes / (1024 * 1024)} MB • SHA-256: ${model.sha256.take(12)}…",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        Button(onClick = { loadModel(model) }, enabled = !loadingModel) {
                            Text(if (loadingModel) "Carregando…" else "Carregar")
                        }
                    }
                }
            }
            Spacer(modifier = Modifier.height(6.dp))
            Button(
                onClick = { modelPicker.launch(arrayOf("application/octet-stream", "application/*", "*/*")) },
                enabled = !importingModel && !loadingModel,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (importingModel) "Importando…" else "Importar modelo GGUF")
            }

            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("Conversa", style = MaterialTheme.typography.titleMedium)
                OutlinedButton(onClick = { createNewConversation() }, enabled = !sending) {
                    Text("Nova conversa")
                }
            }
            Column(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (chatLines.isEmpty()) {
                    Text(
                        "Importe um modelo GGUF compatível, carregue-o e comece a conversar. A primeira carga pode levar algum tempo.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                chatLines.forEach { (role, content) ->
                    Surface(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        color = if (role == "user") MaterialTheme.colorScheme.secondaryContainer
                            else MaterialTheme.colorScheme.surfaceContainerLow,
                    ) {
                        Column(modifier = Modifier.padding(10.dp)) {
                            Text(
                                if (role == "user") "Você" else "Lia",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text(content, style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
                if (sending && chatLines.lastOrNull()?.first == "user") {
                    Text("Lia está pensando…", style = MaterialTheme.typography.bodySmall)
                }
            }

            Spacer(modifier = Modifier.height(8.dp))
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it.take(32_000) },
                modifier = Modifier.fillMaxWidth(),
                enabled = runtimeReady && !sending,
                placeholder = { Text(if (runtimeReady) "Escreva uma mensagem" else "Carregue um modelo para conversar") },
                label = { Text("Mensagem") },
                minLines = 1,
                maxLines = 4,
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (sending) {
                    Button(onClick = { inferenceEngine.cancelGeneration() }, enabled = true) {
                        Text("Parar")
                    }
                } else {
                    Button(onClick = { sendMessage() }, enabled = runtimeReady && draft.isNotBlank()) {
                        Text("Enviar")
                    }
                }
            }
        }
    }
}
