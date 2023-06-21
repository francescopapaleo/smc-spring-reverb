"""" Plotting utilities for the project.
"""

from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import torch
import torchaudio.transforms as T
import librosa

def save_plot(plt, file_name):
    plot_dir = Path('./results/plots')
    plot_dir.mkdir(parents=True, exist_ok=True)
    file_path = plot_dir / (file_name + ".png")
    plt.tight_layout()
    plt.savefig(file_path)
    print(f"Saved plot to {file_path}")


def apply_decorations(ax, legend=False, location="upper right"):
    ax.grid(True)
    if legend:
        ax.legend()
        ax.legend(loc=location)


def plot_data(x, y, subplot, title, x_label, y_label, legend=False):
    subplot.plot(x, y)
    subplot.set_xlim([0, x[-1]])
    subplot.set_title(title)
    subplot.set_xlabel(x_label)
    subplot.set_ylabel(y_label)

    if x_label == "Frequency [Hz]":
        subplot.set_xscale("symlog")
        subplot.set_xlim([20, 12000])
        formatter = ticker.ScalarFormatter()
        formatter.set_scientific(False)
        subplot.xaxis.set_major_formatter(formatter)
        subplot.xaxis.set_minor_formatter(formatter)
        
    apply_decorations(subplot, legend)


def get_time_stamps_np(signal_length, sample_rate):
    return np.arange(0, signal_length / sample_rate, 1 / sample_rate)


def plot_impulse_response(sweep: np.ndarray, inverse_filter: np.ndarray, measured: np.ndarray, sample_rate: int, file_name: str):
    fig, ax = plt.subplots(3, 1, figsize=(15,7))
    plot_data(get_time_stamps_np(len(sweep), sample_rate), sweep, ax[0], "Processed Sweep Tone", "Time [s]", "Amplitude")
    plot_data(get_time_stamps_np(len(inverse_filter), sample_rate), inverse_filter, ax[1], "Inverse Filter", "Time [s]", "Amplitude")
    plot_data(get_time_stamps_np(len(measured), sample_rate), measured, ax[2], "Impulse Response", "Time [s]", "Amplitude")
    fig.suptitle(f"{file_name} - Impulse Response δ(t)")
    save_plot(fig, file_name + "_IR")


def plot_transfer_function(magnitude: np.ndarray, phase: np.ndarray, sample_rate: int, file_name: str):
    freqs = np.linspace(0, sample_rate / 2, len(magnitude))
    fig, ax = plt.subplots(2, 1, figsize=(15, 7))
    plot_data(freqs, magnitude, ax[0], "Transfer Function", "Frequency [Hz]", "Magnitude [dBFS]")
    plot_data(freqs, phase, ax[1], " ", "Frequency [Hz]", "Phase [degrees]")
    plt.suptitle(f"{file_name} - Transfer Function H(w)")
    save_plot(fig, file_name + "_TF")


def plot_rt60(T, energy_db, e_5db, est_rt60, rt60_tgt, file_name):
    plt.subplots(figsize=(15, 4))
    plt.plot(T, energy_db, label="Energy")
    plt.plot([0, est_rt60], [e_5db, -65], "--", label="Linear Fit")
    plt.plot(T, np.ones_like(T) * -60, "--", label="-60 dB")
    plt.vlines(
        est_rt60, energy_db[-1], 0, linestyles="dashed", label="Estimated RT60"
    )

    if rt60_tgt is not None:
        plt.vlines(rt60_tgt, energy_db[-1], 0, label="Target RT60")

    apply_decorations(plt, legend=True, location="lower left")
    
    plt.xlabel("Time [s]")
    plt.ylabel("Energy [dB]")
    plt.ylim([-100, 6])
    plt.title(f"{file_name} RT60 Measurement: {est_rt60 * 1000:.0f} ms")                 
    save_plot(plt, file_name + "_RT60")


def plot_compare_waveform(target, output, sample_rate, title, xlim=None, ylim=None):
    target = target.numpy()
    output = output.numpy()

    target_ch, target_frames = target.shape
    output_ch, output_frames = output.shape
    assert target_ch == output_ch, "Both waveforms must have the same number of channels"
    
    time_target = torch.arange(0, target_frames) / sample_rate
    time_output = torch.arange(0, output_frames) / sample_rate

    figure, axes = plt.subplots(target_ch, 1, figsize=(10, 5))
    if target_ch == 1:
        axes = [axes]
    for c in range(target_ch):
        axes[c].plot(time_target, target[c], linewidth=1, alpha=0.8, label='Target')
        axes[c].plot(time_output, output[c], linewidth=1, alpha=0.8, label='Output')
        axes[c].grid(True)
        if target_ch > 1:
            axes[c].set_ylabel(f'Channel {c+1}')
        else:
            axes[c].set_ylabel('Amplitude')
        axes[c].set_xlabel('Time (s)')
        if xlim:
            axes[c].set_xlim(xlim)
        if ylim:
            axes[c].set_ylim(ylim)
        apply_decorations(axes[c], legend=True)
    figure.suptitle(title)
    plt.tight_layout()
    plt.show(block=False)

    return figure


def plot_compare_spectrogram(target, output, sample_rate, title, t_label="Target", o_label="Output", xlim=None, ylim=None):

    target_ch, target_frames = target.shape
    output_ch, output_frames = output.shape

    figure, axes = plt.subplots(1, 2, figsize=(10, 5))
    waveforms = [target, output]
    labels = [t_label, o_label]
    num_channels = [target_ch, output_ch]

    for idx, ax in enumerate(axes):
        for c in range(num_channels[idx]):
            spectrogram = T.Spectrogram(n_fft=400, win_length=None, hop_length=None, center=True, pad_mode="reflect", power=2.0)(waveforms[idx][c].squeeze())
            im = ax.imshow(librosa.power_to_db(spectrogram), origin="lower", aspect="auto")
            ax.set_yticks(np.linspace(0, spectrogram.shape[0], 5))  # set 5 y-ticks
            ax.set_yticklabels(np.linspace(0, sample_rate / 2, 5).astype(int))  # label them with the corresponding frequency values
            if num_channels[idx] > 1:
                ax.set_ylabel(f'Channel {c+1}')
            else:
                ax.set_ylabel("Frequency [Hz]")
            ax.set_xlabel("Frames")
            if xlim:
                ax.set_xlim(xlim)
            if ylim:
                ax.set_ylim(ylim)
            ax.set_title(labels[idx])
            figure.suptitle(title)
            figure.colorbar(im, ax=ax)
    plt.tight_layout()
    plt.show(block=False)

    return figure


if __name__ == "__main__":
    print("This module is not intended to be executed directly. Do it only for debugging purposes.")