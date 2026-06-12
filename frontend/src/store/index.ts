import { configureStore } from '@reduxjs/toolkit';
import disasterReducer from './slices/disasterSlice';

export const store = configureStore({
  reducer: {
    disaster: disasterReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
