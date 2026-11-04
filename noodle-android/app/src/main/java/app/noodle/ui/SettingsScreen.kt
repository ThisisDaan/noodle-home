package app.noodle.ui

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.noodle.NoodleViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(vm: NoodleViewModel, back: () -> Unit) {
    var reporting by remember { mutableStateOf(vm.prefs.reporting) }
    var notifications by remember { mutableStateOf(vm.prefs.notifications) }
    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { vm.setNotifications(notifications) }

    // Android asks for background location separately, and only after foreground location was granted.
    val background = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { vm.reportNow() }
    val foreground = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        background.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
    }

    Scaffold(topBar = {
        TopAppBar(title = { Text("Settings") }, navigationIcon = {
            IconButton(onClick = back) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
        })
    }) { padding ->
        Column(Modifier.padding(padding).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text("Server", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
            Text(vm.prefs.baseUrl)

            Text("This phone", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Report to Noodle as ${vm.prefs.phoneName}")
                    Text("Battery, charging and whether you are home, about every 15 minutes.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(reporting, { reporting = it; vm.setReporting(it) })
            }
            Text("Notifications", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Notifications on this network")
                    Text("Works at home (or over a VPN) without internet. Keeps a small notification so Android lets Noodle listen.",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Switch(notifications, {
                    notifications = it
                    vm.setNotifications(it)
                    if (it) askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
                })
            }

            OutlinedButton(
                onClick = {
                    foreground.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
                },
                enabled = reporting,
            ) { Text("Allow location (home / away)") }
            OutlinedButton(onClick = { vm.reportNow() }, enabled = reporting) { Text("Report now") }

            OutlinedButton(onClick = { vm.logout() }) { Text("Log out") }
        }
    }
}
