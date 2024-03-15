export const DefaultReducer = (currentState, action) => {
  console.log(action)
  switch (action.type) {
    case 'MQTT_STATUS':
      return {
        ...currentState,
        connected: action.connected
      };
    default:
      throw new Error(`Unhandled action type: ${action.type}`);
  }
};