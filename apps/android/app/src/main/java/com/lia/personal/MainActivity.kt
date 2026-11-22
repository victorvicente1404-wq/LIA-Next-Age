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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
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
import com.lia.personal.inference.LiaModelStore
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
    val scope = rememberCoroutineScope()
    var storageReady by remember { mutableStateOf(false) }
    var storageError by remember { mutableStateOf(false) }
    var conversationCount by remember { mutableIntStateOf(0) }
    var importingModel by remember { mutableStateOf(false) }
    var modelStatus by remember { mutableStateOf("Verificando modelos locais…") }
    var importedModels by remember { mutableStateOf<List<ImportedModel>>(emptyList()) }

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
                    modelStatus = "Catálogo local atualizado. Arquivos importados não estão carregados no motor de IA."
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
                if (conversations.isEmpty()) {
                    repository.createConversation("Conversa inicial")
                }
                repository.listConversations().size to modelStore.listImportedModels()
            }
            conversationCount = initialState.first
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
    DisposableEffect(storage) {
        onDispose { storage.close() }
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
                .padding(horizontal = 20.dp, vertical = 16.dp),
        ) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(18.dp),
                color = MaterialTheme.colorScheme.surfaceContainer,
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text(
                        text = when {
                            storageReady -> "Armazenamento local preparado"
                            storageError -> "Não foi possível abrir o armazenamento local"
                            else -> "Preparando armazenamento local…"
                        },
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = if (storageReady) {
                            "$conversationCount conversa(s) guardada(s) neste aparelho. " +
                                "O histórico e as memórias explícitas usam o repositório local. " +
                                "Nenhuma mensagem é enviada para um serviço remoto."
                        } else {
                            "O histórico de conversas e as memórias explícitas ficam separados " +
                                "no próprio aparelho. Nenhuma mensagem será enviada para um " +
                                "serviço remoto."
                        },
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Spacer(modifier = Modifier.height(18.dp))
            Text("Modelo de IA", style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                modelStatus,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            importedModels.forEach { model ->
                Spacer(modifier = Modifier.height(8.dp))
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerLow,
                ) {
                    Column(modifier = Modifier.padding(12.dp)) {
                        Text(model.originalName, style = MaterialTheme.typography.bodyMedium)
                        Text(
                            "${model.sizeBytes / (1024 * 1024)} MB • SHA-256: ${model.sha256.take(16)}…",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(
                            "Importado; ainda não carregado no motor de IA.",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            Spacer(modifier = Modifier.height(10.dp))
            Button(
                onClick = { modelPicker.launch(arrayOf("application/octet-stream", "application/*", "*/*")) },
                enabled = !importingModel,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (importingModel) "Importando…" else "Selecionar modelo GGUF")
            }
            Text(
                "A importação apenas guarda e verifica o arquivo. O motor de IA ainda precisa ser conectado antes de conversar.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(modifier = Modifier.weight(1f))

            OutlinedTextField(
                value = "",
                onValueChange = {},
                modifier = Modifier.fillMaxWidth(),
                enabled = false,
                placeholder = { Text("A conversa será ativada quando o modelo local estiver pronto") },
                label = { Text("Mensagem") },
                minLines = 1,
                maxLines = 4,
            )
            Spacer(modifier = Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Button(onClick = {}, enabled = false) {
                    Text("Enviar")
                }
            }
        }
    }
}
