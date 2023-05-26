from config import parser, model_params
from tcn import TCN

from utils.data import SpringDataset

from pathlib import Path

import h5py
import os
import sys
import tqdm
import numpy as np
import soundfile as sf
import tempfile

import torch
from torch.utils.tensorboard import SummaryWriter
import torchsummary

import torchaudio.transforms as T
import torchvision

import auraloss

import matplotlib.pyplot as plt

args = parser.parse_args()

torch.backends.cudnn.benchmark = True
torch.manual_seed(args.seed)

print("## Loading data...")
transforms = torchvision.transforms.Compose([torchvision.transforms.ToTensor()])

dataset = SpringDataset(root_dir=args.data_dir, split='train')
train_dataset = SpringDataset(root_dir=args.data_dir, split='train')

train_size = int(0.8 * len(dataset))
val_size = len(dataset) - train_size

train, valid = torch.utils.data.random_split(dataset, [train_size, val_size])

trainloader = torch.utils.data.DataLoader(train, batch_size=32)
validloader = torch.utils.data.DataLoader(valid, batch_size=32)


print("## Instantiating model...")

device = torch.device(args.device)
model = TCN(
    n_inputs=1,
    n_outputs=1,
    cond_dim=model_params["cond_dim"], 
    kernel_size=1, 
    n_blocks=model_params["n_blocks"], 
    dilation_growth=model_params["dilation_growth"], 
    n_channels=model_params["n_channels"],
    )
model = model.to(args.device)  # move the model to the right device

# setup loss function and optimizer
criterion = auraloss.freq.MultiResolutionSTFTLoss(
    fft_sizes=[32, 128, 512, 2048],
    win_lengths=[32, 128, 512, 2048],
    hop_sizes=[16, 64, 256, 1024]
)
torchsummary.summary(model, [(1,65536), (1,2)], device=args.device)

optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

mse = torch.nn.MSELoss()
mse__values = []

esr = auraloss.time.ESRLoss()
l1__values = []

snr = auraloss.time.SNRLoss()
esr__ = []

epochs = 10
min_valid_loss = np.inf
model = model.float()

from torch.utils.tensorboard import SummaryWriter
writer = SummaryWriter()

global_step = 0

print('Training started...')
model.train()
train_loss = 0.0
for e in range(epochs):
    for input, target in trainloader:
        
        input = input.float().to(args.device)
        target = target.float().to(args.device)
        c = torch.tensor([0.0, 0.0], device=device).view(1,1,-1)

        rf = model.compute_receptive_field()
        input_pad = torch.nn.functional.pad(input, (rf-1, 0))
        
        optimizer.zero_grad()        # Clear the gradients
       
        output = model(input_pad.float(), c)     # Forward Pass
        
        loss = criterion(output, target)    # Find the Loss
        loss.backward()          # Calculate gradients 
        
        optimizer.step()        # Update Weights
    
        train_loss += loss.item()       # Calculate Loss
    
        mse_loss = mse(output, target)
        esr_loss = esr(output, target)
        snr_loss = snr(output, target)

        # Log the training loss
        writer.add_scalar('Loss/Train', loss.item(), global_step)
        writer.add_scalar('Loss/MSE', mse_loss.item(), global_step)
        writer.add_scalar('Loss/ESR', esr_loss.item(), global_step)
        writer.add_scalar('Loss/SNR', snr_loss.item(), global_step)

        # Getting the weights of the first layer of the model
        weights = next(model.parameters()).cpu().data
        writer.add_histogram('Weights', weights, global_step)
        global_step += 1
    
    print('Validation Loop')
    valid_loss = 0.0
    model.eval()
    for input, target in validloader:

        input, target = input.to(args.device), target.to(args.device)
        
        # Forward Pass
        output = model(input.float(), c)
        # Find the Loss
        loss = criterion(output, target)
        # Calculate Loss
        valid_loss += loss.item()

    # Print and log the training loss
    print(f'Epoch {e+1} \t\t Training Loss: {train_loss / len(trainloader)} \t\t Validation Loss: {valid_loss / len(validloader)}')
    
    if min_valid_loss > valid_loss:
        print(f'Validation loss decreased ({min_valid_loss:.6f} --> {valid_loss:.6f}).  Saving model ...''')
        min_valid_loss = valid_loss
        
        save_to = Path(args.models_dir) / args.save
        torch.save(model.state_dict(), save_to)

# Close the TensorBoard writer
writer.close()

if __name__ == "__main__":
    parser.parse_args()
