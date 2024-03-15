export async function custom_new_message_action(dispatch, message) {
  console.log(message)
}

export const CustomReducer = (currentState, action) => {
  // console.log(action)
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

// export {custom_new_message_action, CustomReducer}