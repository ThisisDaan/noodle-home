/** Which device's card is being designed in CardDesigner (null = closed). */
class CardDesigner {
	deviceId = $state<string | null>(null);

	open(deviceId: string) {
		this.deviceId = deviceId;
	}

	close() {
		this.deviceId = null;
	}
}

export const cardDesigner = new CardDesigner();
