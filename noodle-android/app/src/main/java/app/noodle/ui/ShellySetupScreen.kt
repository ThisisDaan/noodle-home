package app.noodle.ui

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.location.LocationManager
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LifecycleResumeEffect
import app.noodle.ShellySetup
import app.noodle.ShellySetupViewModel

/** Android 13+ has a Wi-Fi permission of its own; before that, listing Wi-Fi networks needs the location permission. */
private val NEEDED = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) Manifest.permission.NEARBY_WIFI_DEVICES
else Manifest.permission.ACCESS_FINE_LOCATION

private fun granted(ctx: Context, permission: String) =
    ContextCompat.checkSelfPermission(ctx, permission) == PackageManager.PERMISSION_GRANTED

/**
 * Puts a new Shelly (Gen1 included, which has no Bluetooth) on the home Wi-Fi with this phone's Wi-Fi. The nearby
 * networks are only looked at while this screen is open. The password is kept in this screen only, never saved.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShellySetupScreen(vm: ShellySetupViewModel, back: () -> Unit) {
    val ctx = LocalContext.current
    val state by vm.state.collectAsState()

    // Checked again whenever the screen comes back (the user may have changed it in Android's settings).
    var allowed by remember { mutableStateOf(granted(ctx, NEEDED)) }
    var asked by remember { mutableStateOf(false) }
    var wifiOn by remember { mutableStateOf(true) }
    var locationOn by remember { mutableStateOf(true) }
    LifecycleResumeEffect(Unit) {
        allowed = granted(ctx, NEEDED)
        wifiOn = ctx.getSystemService(WifiManager::class.java)?.isWifiEnabled != false
        locationOn = Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU ||
            ctx.getSystemService(LocationManager::class.java)?.isLocationEnabled != false
        onPauseOrDispose {}
    }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        asked = true
        allowed = granted(ctx, NEEDED)
    }
    fun askPermission() {
        // On Android 13+ location is optional: it only lets Noodle fill in the name of the Wi-Fi this phone is on.
        val extra = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) arrayOf(Manifest.permission.ACCESS_FINE_LOCATION) else emptyArray()
        ask.launch(arrayOf(NEEDED) + extra)
    }
    val ready = allowed && wifiOn && locationOn

    // Listen for Android's list of networks only while this screen is open and allowed to; nothing scans otherwise.
    DisposableEffect(ready) {
        if (!ready) return@DisposableEffect onDispose {}
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) = vm.readNearby()
        }
        ContextCompat.registerReceiver(ctx, receiver, IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION), ContextCompat.RECEIVER_NOT_EXPORTED)
        vm.search()
        onDispose { runCatching { ctx.unregisterReceiver(receiver) } }
    }

    var picked by remember { mutableStateOf<String?>(null) }
    var homeSsid by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") } // not rememberSaveable: it must not end up in saved state
    var showPassword by remember { mutableStateOf(false) }
    var menuOpen by remember { mutableStateOf(false) }
    LaunchedEffect(state.current, state.nearby.homes) {
        if (homeSsid.isEmpty()) homeSsid = state.current ?: state.nearby.homes.firstOrNull()?.ssid ?: ""
    }
    LaunchedEffect(state.done) { if (state.done != null) { password = ""; picked = null } }

    Scaffold(topBar = {
        TopAppBar(title = { Text("Set up a new Shelly") }, navigationIcon = {
            IconButton(onClick = back) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
        })
    }) { padding ->
        Column(
            Modifier.padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text("A new Shelly opens its own Wi-Fi until it is set up. This phone joins it for a moment and gives it " +
                "your Wi-Fi details, then Noodle adds it. Keep the phone close to the Shelly.",
                style = MaterialTheme.typography.bodyMedium)

            when {
                !allowed -> Notice(
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU)
                        "Android only shows nearby Wi-Fi networks to apps you allow. Noodle looks for the Shelly's own Wi-Fi " +
                            "while this screen is open, nothing more. Allowing location as well is optional: it lets Noodle " +
                            "fill in the name of the Wi-Fi this phone is on."
                    else
                        "On this Android version, apps may only list nearby Wi-Fi networks with the location permission. " +
                            "Noodle uses it to find the Shelly's own Wi-Fi while this screen is open; it does not track where you are.",
                ) {
                    Button(onClick = ::askPermission) { Text("Allow") }
                    if (asked) OutlinedButton(onClick = {
                        ctx.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", ctx.packageName, null)))
                    }) { Text("Open app settings") }
                }
                !wifiOn -> Notice("This phone's Wi-Fi is off. Turn it on, then come back here.") {
                    OutlinedButton(onClick = { ctx.startActivity(Intent(Settings.Panel.ACTION_WIFI)) }) { Text("Wi-Fi settings") }
                }
                !locationOn -> Notice("Android only lists Wi-Fi networks while Location is on. Turn on Location, then come back here.") {
                    OutlinedButton(onClick = { ctx.startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)) }) { Text("Location settings") }
                }
                else -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("New Shellies nearby", Modifier.weight(1f), style = MaterialTheme.typography.titleSmall,
                            color = MaterialTheme.colorScheme.primary)
                        TextButton(onClick = vm::search, enabled = !state.busy) {
                            Icon(Icons.Default.Refresh, contentDescription = null, Modifier.size(18.dp)); Text(" Search again")
                        }
                    }
                    val shellies = state.nearby.shellies
                    if (shellies.isEmpty()) {
                        Text(if (state.looked) "No new Shelly heard. Power it on (or reset it: hold its button for about 10 seconds), " +
                            "wait a moment, then search again." else "Looking…",
                            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    shellies.forEach { net ->
                        Row(
                            Modifier.fillMaxWidth().clickable(enabled = !state.busy) { picked = net.ssid },
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            RadioButton(selected = picked == net.ssid, onClick = { picked = net.ssid }, enabled = !state.busy)
                            Column {
                                Text(ShellySetup.apName(net.ssid))
                                Text("New: not on your Wi-Fi yet · ${net.ssid}", style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }

                    val shelly = picked?.takeIf { p -> shellies.any { it.ssid == p } || state.busy }
                    if (shelly != null) {
                        Text("Noodle puts this Shelly on your Wi-Fi. Pick the network it should join.", style = MaterialTheme.typography.bodyMedium)
                        ExposedDropdownMenuBox(expanded = menuOpen, onExpandedChange = { menuOpen = it && !state.busy }) {
                            OutlinedTextField(
                                value = homeSsid, onValueChange = { homeSsid = it }, singleLine = true, enabled = !state.busy,
                                label = { Text("Wi-Fi name") },
                                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(menuOpen) },
                                modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryEditable),
                            )
                            ExposedDropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                                state.nearby.homes.forEach { net ->
                                    val note = (if (net.ssid == state.current) " (this phone)" else "") +
                                        (if (state.nearby.only5(net.ssid)) " (5 GHz only?)" else "")
                                    DropdownMenuItem(text = { Text(net.ssid + note) }, onClick = { homeSsid = net.ssid; menuOpen = false })
                                }
                            }
                        }
                        OutlinedTextField(
                            value = password, onValueChange = { password = it }, singleLine = true, enabled = !state.busy,
                            label = { Text("Wi-Fi password") }, modifier = Modifier.fillMaxWidth(),
                            visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
                            trailingIcon = {
                                IconButton(onClick = { showPassword = !showPassword }) {
                                    Icon(if (showPassword) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                                        contentDescription = if (showPassword) "Hide password" else "Show password")
                                }
                            },
                        )
                        Text("Shellies only join 2.4 GHz networks. The password goes to the Shelly and is not saved.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        if (state.nearby.only5(homeSsid)) {
                            Notice("This phone only hears $homeSsid on 5 GHz, which a Shelly cannot join. Pick it anyway if your " +
                                "router also has 2.4 GHz under this name.")
                        }
                        Text("Android asks whether Noodle may connect to the Shelly's Wi-Fi: tap Connect. This phone is off your " +
                            "Wi-Fi for about a minute while it sets the Shelly up.",
                            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        if (state.busy) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                                Text(state.step ?: "", color = MaterialTheme.colorScheme.primary)
                            }
                        } else {
                            Button(onClick = { vm.setUp(shelly, homeSsid.trim(), password) }, enabled = homeSsid.isNotBlank()) {
                                Text("Set up")
                            }
                        }
                    }
                }
            }

            state.error?.let { Notice(it, error = true) { TextButton(onClick = vm::dismiss) { Text("OK") } } }
            state.done?.let { Notice(it) { Button(onClick = { vm.dismiss(); back() }) { Text("Done") } } }
        }
    }
}

@Composable
private fun Notice(text: String, error: Boolean = false, actions: (@Composable () -> Unit)? = null) {
    Card(colors = if (error) CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)
    else CardDefaults.cardColors()) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(text, style = MaterialTheme.typography.bodyMedium)
            if (actions != null) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { actions() }
        }
    }
}
